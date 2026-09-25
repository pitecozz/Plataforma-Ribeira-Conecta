"""Cleanup for explicitly synthetic PostgreSQL integration-test tenants."""

from __future__ import annotations

from collections import defaultdict
import os

import psycopg
from psycopg import sql
from psycopg.rows import dict_row


def delete_test_tenants(tenant_ids: list[str]) -> None:
    """Delete only test-created tenants and their tenant-scoped dependents.

    PostgreSQL's tenant foreign keys intentionally do not cascade: production
    data must never disappear because a tenant row is removed.  Integration
    tests therefore delete their own child rows in dependency order.
    """
    if not tenant_ids:
        return
    dsn = os.getenv("RIBEIRA_TEST_MIGRATION_DATABASE_URL")
    if not dsn:
        raise RuntimeError(
            "RIBEIRA_TEST_MIGRATION_DATABASE_URL is required for cleanup"
        )
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        # Job output and derived product deliberately reference each other for
        # durable provenance. Break that cycle only for test-created tenants
        # before dependency-ordered deletion below.
        connection.execute(
            "UPDATE processing_job SET output_product_id=NULL "
            "WHERE tenant_id = ANY(%s)",
            (tenant_ids,),
        )
        tables = {
            row["table_name"]
            for row in connection.execute(
                "SELECT table_name FROM information_schema.columns "
                "WHERE table_schema='public' AND column_name='tenant_id'"
            ).fetchall()
        }
        relationships = connection.execute(
            """SELECT conrelid::regclass::text AS child,
                      confrelid::regclass::text AS parent
               FROM pg_constraint
               WHERE contype='f' AND connamespace='public'::regnamespace"""
        ).fetchall()
        children: dict[str, set[str]] = defaultdict(set)
        for row in relationships:
            child = str(row["child"]).removeprefix("public.")
            parent = str(row["parent"]).removeprefix("public.")
            if child in tables and parent in tables:
                children[parent].add(child)

        order: list[str] = []
        visited: set[str] = set()

        def visit(table: str) -> None:
            if table in visited:
                return
            visited.add(table)
            for child in sorted(children[table]):
                visit(child)
            order.append(table)

        for table in sorted(tables):
            visit(table)
        # The durable job/product provenance link is cyclic. Its reverse
        # output pointer was cleared above, so delete the product before the
        # job while preserving child-before-parent ordering everywhere else.
        if "derived_product" in order and "processing_job" in order:
            order.remove("derived_product")
            order.insert(order.index("processing_job"), "derived_product")
        if "field_context_boundary_version" in tables:
            connection.execute(
                "ALTER TABLE field_context_boundary_version DISABLE TRIGGER USER"
            )
        for table in order:
            if table != "tenant":
                connection.execute(
                    sql.SQL("DELETE FROM {} WHERE tenant_id = ANY(%s)").format(
                        sql.Identifier(table)
                    ),
                    (tenant_ids,),
                )
        if "field_context_boundary_version" in tables:
            connection.execute(
                "ALTER TABLE field_context_boundary_version ENABLE TRIGGER USER"
            )
        connection.execute("DELETE FROM tenant WHERE id = ANY(%s)", (tenant_ids,))

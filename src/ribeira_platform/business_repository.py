from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Iterable

from .business import (
    Asset,
    AssetOwnership,
    CapexItem,
    CommercialClassification,
    CommercialOpportunity,
    ContractVersion,
    Customer,
    CustomerContract,
    InstallationProject,
    OperationalCapacityPolicy,
    PricingPolicy,
    PricingPolicyVersion,
    Product,
    PassThroughItem,
    ProspectScoringFactor,
    ProspectScoringModelVersion,
    ServiceOffering,
    ServicePlan,
    Subscription,
    money,
)
from .models import new_id, now_utc
from .time_utils import parse_aware


SQLITE_BUSINESS_SCHEMA = """
CREATE TABLE IF NOT EXISTS customer (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, customer_type TEXT NOT NULL, display_name TEXT NOT NULL, legal_name TEXT, status TEXT NOT NULL, data_classification TEXT NOT NULL, external_reference TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS customer_property (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, customer_id TEXT NOT NULL, property_id TEXT NOT NULL, relationship_type TEXT NOT NULL, valid_from TEXT NOT NULL, valid_until TEXT, data_classification TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS product (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, sku TEXT, name TEXT NOT NULL, category TEXT NOT NULL, status TEXT NOT NULL, description TEXT, data_classification TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS service (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, product_id TEXT, name TEXT NOT NULL, category TEXT NOT NULL, status TEXT NOT NULL, recurring INTEGER NOT NULL, revenue_type TEXT NOT NULL, data_classification TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS service_plan (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, service_id TEXT NOT NULL, name TEXT NOT NULL, billing_period TEXT NOT NULL, monthly_price TEXT, currency TEXT NOT NULL, status TEXT NOT NULL, revenue_treatment TEXT NOT NULL, data_classification TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS customer_contract (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, customer_id TEXT NOT NULL, property_id TEXT, contract_type TEXT NOT NULL, counterparty_name TEXT, external_provider_name TEXT, ribeira_revenue_treatment TEXT NOT NULL, status TEXT NOT NULL, start_at TEXT NOT NULL, end_at TEXT, data_classification TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS contract_version (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, contract_id TEXT NOT NULL, version INTEGER NOT NULL, status TEXT NOT NULL, valid_from TEXT NOT NULL, valid_until TEXT, total_price TEXT, currency TEXT NOT NULL, recurring INTEGER NOT NULL, configuration TEXT NOT NULL, created_by TEXT NOT NULL, approved_by TEXT, data_classification TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS subscription (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, contract_id TEXT NOT NULL, contract_version_id TEXT NOT NULL, service_plan_id TEXT NOT NULL, status TEXT NOT NULL, start_at TEXT NOT NULL, end_at TEXT, monthly_price TEXT, currency TEXT NOT NULL, recurring INTEGER NOT NULL, mrr_eligible INTEGER NOT NULL, revenue_treatment TEXT NOT NULL, data_classification TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS site (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, property_id TEXT NOT NULL, name TEXT NOT NULL, site_type TEXT NOT NULL, geometry_geojson TEXT, geometry_crs TEXT, data_classification TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS installation_project (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, customer_id TEXT NOT NULL, property_id TEXT, name TEXT NOT NULL, status TEXT NOT NULL, technical_provider_type TEXT NOT NULL, customer_total_project_cost TEXT, currency TEXT NOT NULL, ribeira_revenue_treatment TEXT NOT NULL, data_classification TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS asset (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, asset_type TEXT NOT NULL, name TEXT NOT NULL, serial_number TEXT, status TEXT NOT NULL, property_id TEXT, site_id TEXT, data_classification TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS asset_ownership (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, asset_id TEXT NOT NULL, ownership_kind TEXT NOT NULL, customer_id TEXT, purchased_by TEXT, maintained_by TEXT, replacement_responsibility TEXT, risk_bearer TEXT, valid_from TEXT NOT NULL, valid_until TEXT, acquisition_document TEXT, data_classification TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS installation (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, asset_id TEXT, status TEXT NOT NULL, installed_at TEXT, one_time_revenue TEXT, currency TEXT NOT NULL, ownership_kind TEXT NOT NULL, data_classification TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS capex_item (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, project_id TEXT, asset_id TEXT, description TEXT NOT NULL, amount TEXT, currency TEXT NOT NULL, capex_classification TEXT NOT NULL, ownership_kind TEXT NOT NULL, purchased_by TEXT, source TEXT, data_classification TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS cost_item (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, project_id TEXT, customer_contract_id TEXT, cost_type TEXT NOT NULL, amount TEXT, currency TEXT NOT NULL, is_net_margin_component INTEGER NOT NULL, source TEXT, data_classification TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS revenue_item (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, project_id TEXT, customer_contract_id TEXT, revenue_type TEXT NOT NULL, amount TEXT, currency TEXT NOT NULL, recognized_by_ribeira INTEGER NOT NULL, recurring INTEGER NOT NULL, source TEXT, data_classification TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS pass_through_item (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, project_id TEXT, customer_id TEXT, description TEXT NOT NULL, amount TEXT, currency TEXT NOT NULL, supplier TEXT, document_reference TEXT, paid_at TEXT, data_classification TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS pricing_policy (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, name TEXT NOT NULL, scope TEXT NOT NULL, status TEXT NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS pricing_policy_version (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, pricing_policy_id TEXT NOT NULL, version INTEGER NOT NULL, status TEXT NOT NULL, lower_threshold TEXT NOT NULL, lower_rate TEXT NOT NULL, lower_minimum TEXT NOT NULL, upper_rate TEXT NOT NULL, upper_minimum TEXT NOT NULL, currency TEXT NOT NULL, valid_from TEXT NOT NULL, valid_until TEXT, created_by TEXT NOT NULL, approved_by TEXT, data_classification TEXT NOT NULL, source TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS operational_capacity_policy (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, scope TEXT NOT NULL, capacity_type TEXT NOT NULL, value TEXT NOT NULL, unit TEXT NOT NULL, effective_from TEXT NOT NULL, effective_until TEXT, status TEXT NOT NULL, created_by TEXT NOT NULL, approved_by TEXT, source TEXT NOT NULL, data_classification TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS commercial_rule (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, name TEXT NOT NULL, authority TEXT NOT NULL, status TEXT NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS commercial_rule_version (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, commercial_rule_id TEXT NOT NULL, version INTEGER NOT NULL, condition TEXT NOT NULL, action TEXT NOT NULL, status TEXT NOT NULL, valid_from TEXT NOT NULL, valid_until TEXT, created_by TEXT NOT NULL, approved_by TEXT, data_classification TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS commercial_opportunity (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, customer_id TEXT NOT NULL, property_id TEXT, opportunity_type TEXT NOT NULL, status TEXT NOT NULL, classification TEXT NOT NULL, score TEXT, evidence_ids TEXT NOT NULL, rule_id TEXT, rule_version INTEGER, estimated_value TEXT, estimated_value_classification TEXT NOT NULL, created_at TEXT NOT NULL, closed_at TEXT, outcome TEXT);
CREATE TABLE IF NOT EXISTS opportunity_evidence (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, opportunity_id TEXT NOT NULL, evidence_id TEXT NOT NULL, role TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS prospect_scoring_model (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, name TEXT NOT NULL, status TEXT NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS prospect_scoring_model_version (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, model_id TEXT NOT NULL, version INTEGER NOT NULL, status TEXT NOT NULL, unknown_policy TEXT NOT NULL, valid_from TEXT NOT NULL, valid_until TEXT, created_by TEXT NOT NULL, approved_by TEXT, data_classification TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS prospect_scoring_factor (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, model_version_id TEXT NOT NULL, factor_key TEXT NOT NULL, description TEXT NOT NULL, condition TEXT NOT NULL, points INTEGER NOT NULL, unknown_policy TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL);
"""

VERSION_TABLES = frozenset(
    {
        "contract_version",
        "pricing_policy_version",
        "operational_capacity_policy",
        "commercial_rule_version",
    }
)


class BusinessRepository:
    """Persistence adapter for business aggregates.

    The application transaction and PostgreSQL RLS context are owned by the
    existing store. This adapter only translates domain records to SQL.
    """

    def __init__(self, store: Any) -> None:
        self.store = store
        self.connection = store.connection
        self.postgres = store.__class__.__name__ == "PostgresStore"
        if not self.postgres:
            self.connection.executescript(SQLITE_BUSINESS_SCHEMA)

    @property
    def placeholder(self) -> str:
        return "%s" if self.postgres else "?"

    def _execute(self, sql: str, params: Iterable[Any] = ()) -> Any:
        return self.connection.execute(sql, tuple(params))

    def _one(self, sql: str, params: Iterable[Any] = ()) -> Any:
        return self._execute(sql, params).fetchone()

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _decimal(value: Any) -> Decimal | None:
        return None if value is None else Decimal(str(value))

    @staticmethod
    def _timestamp(value: Any) -> str | None:
        return (
            None
            if value is None
            else (value.isoformat() if hasattr(value, "isoformat") else str(value))
        )

    @staticmethod
    def _classification(value: Any) -> CommercialClassification:
        return CommercialClassification(str(value))

    @staticmethod
    def _active_window(valid_from: Any, valid_until: Any, at: str) -> bool:
        instant = parse_aware(at)
        starts = parse_aware(
            valid_from.isoformat()
            if hasattr(valid_from, "isoformat")
            else str(valid_from)
        )
        if instant < starts:
            return False
        if valid_until is None:
            return True
        ends = parse_aware(
            valid_until.isoformat()
            if hasattr(valid_until, "isoformat")
            else str(valid_until)
        )
        return instant < ends

    def _insert(self, table: str, columns: list[str], values: list[Any]) -> None:
        if not table.isidentifier() or any(
            not column.isidentifier() for column in columns
        ):
            raise ValueError("repository SQL identifiers must be internal names")
        marks = ",".join([self.placeholder] * len(columns))
        bind_values = [
            str(value) if isinstance(value, Decimal) else value for value in values
        ]
        self._execute(
            f"INSERT INTO {table}({','.join(columns)}) VALUES ({marks})",  # nosec B608 - identifiers are internal repository constants
            bind_values,
        )

    def create_customer(self, item: Customer) -> Customer:
        self._insert(
            "customer",
            [
                "id",
                "tenant_id",
                "customer_type",
                "display_name",
                "legal_name",
                "status",
                "data_classification",
                "external_reference",
                "created_at",
            ],
            [
                item.id,
                item.tenant_id,
                item.customer_type,
                item.display_name,
                item.legal_name,
                item.status,
                item.classification.value,
                item.external_reference,
                item.created_at or now_utc(),
            ],
        )
        return item

    def get_customer(self, tenant_id: str, customer_id: str) -> Customer | None:
        row = self._one(
            f"SELECT * FROM customer WHERE tenant_id={self.placeholder} AND id={self.placeholder}",  # nosec B608 - only placeholders are interpolated
            [tenant_id, customer_id],
        )
        if row is None:
            return None
        return Customer(
            str(row["id"]),
            str(row["tenant_id"]),
            row["customer_type"],
            row["display_name"],
            row["legal_name"],
            row["status"],
            self._classification(row["data_classification"]),
            row["external_reference"],
            self._timestamp(row["created_at"]),
        )

    def create_customer_property(
        self,
        tenant_id: str,
        customer_id: str,
        property_id: str,
        relationship_type: str,
        valid_from: str,
        valid_until: str | None,
        classification: CommercialClassification,
    ) -> str:
        item_id = new_id()
        self._insert(
            "customer_property",
            [
                "id",
                "tenant_id",
                "customer_id",
                "property_id",
                "relationship_type",
                "valid_from",
                "valid_until",
                "data_classification",
                "created_at",
            ],
            [
                item_id,
                tenant_id,
                customer_id,
                property_id,
                relationship_type,
                valid_from,
                valid_until,
                classification.value,
                now_utc(),
            ],
        )
        return item_id

    def create_product(self, item: Product) -> Product:
        self._insert(
            "product",
            [
                "id",
                "tenant_id",
                "sku",
                "name",
                "category",
                "status",
                "description",
                "data_classification",
                "created_at",
            ],
            [
                item.id,
                item.tenant_id,
                item.sku,
                item.name,
                item.category,
                item.status.value,
                item.description,
                item.classification.value,
                now_utc(),
            ],
        )
        return item

    def create_service(self, item: ServiceOffering) -> ServiceOffering:
        self._insert(
            "service",
            [
                "id",
                "tenant_id",
                "product_id",
                "name",
                "category",
                "status",
                "recurring",
                "revenue_type",
                "data_classification",
                "created_at",
            ],
            [
                item.id,
                item.tenant_id,
                item.product_id,
                item.name,
                item.category,
                item.status.value,
                item.recurring,
                item.revenue_type.value,
                item.classification.value,
                now_utc(),
            ],
        )
        return item

    def create_service_plan(self, item: ServicePlan) -> ServicePlan:
        self._insert(
            "service_plan",
            [
                "id",
                "tenant_id",
                "service_id",
                "name",
                "billing_period",
                "monthly_price",
                "currency",
                "status",
                "revenue_treatment",
                "data_classification",
                "created_at",
            ],
            [
                item.id,
                item.tenant_id,
                item.service_id,
                item.name,
                item.billing_period,
                item.monthly_price,
                item.currency,
                item.status,
                item.revenue_treatment.value,
                item.classification.value,
                now_utc(),
            ],
        )
        return item

    def create_contract(self, item: CustomerContract) -> CustomerContract:
        self._insert(
            "customer_contract",
            [
                "id",
                "tenant_id",
                "customer_id",
                "property_id",
                "contract_type",
                "counterparty_name",
                "external_provider_name",
                "ribeira_revenue_treatment",
                "status",
                "start_at",
                "end_at",
                "data_classification",
                "created_at",
            ],
            [
                item.id,
                item.tenant_id,
                item.customer_id,
                item.property_id,
                item.contract_type,
                item.counterparty_name,
                item.external_provider_name,
                item.revenue_treatment.value,
                item.status,
                item.start_at,
                item.end_at,
                item.classification.value,
                item.created_at or now_utc(),
            ],
        )
        return item

    def create_contract_version(self, item: ContractVersion) -> ContractVersion:
        self._insert(
            "contract_version",
            [
                "id",
                "tenant_id",
                "contract_id",
                "version",
                "status",
                "valid_from",
                "valid_until",
                "total_price",
                "currency",
                "recurring",
                "configuration",
                "created_by",
                "approved_by",
                "data_classification",
                "created_at",
            ],
            [
                item.id,
                item.tenant_id,
                item.contract_id,
                item.version,
                item.status,
                item.valid_from,
                item.valid_until,
                item.total_price,
                item.currency,
                item.recurring,
                self._json(item.configuration),
                item.created_by,
                item.approved_by,
                item.classification.value,
                now_utc(),
            ],
        )
        return item

    def approve_version(
        self,
        table: str,
        tenant_id: str,
        version_id: str,
        approver: str,
        parent_column: str | None = None,
        parent_id: str | None = None,
    ) -> None:
        if table not in VERSION_TABLES:
            raise ValueError("unsupported business version table")
        if (parent_column is None) != (parent_id is None):
            raise ValueError("parent column and id must be supplied together")
        if parent_column is not None and not parent_column.isidentifier():
            raise ValueError("repository SQL identifiers must be internal names")
        p = self.placeholder
        parent_filter = f" AND {parent_column}={p}" if parent_column else ""
        lookup_params = [tenant_id, version_id]
        if parent_id is not None:
            lookup_params.append(parent_id)
        row = self._one(
            f"SELECT created_by, status FROM {table} WHERE tenant_id={p} AND id={p}{parent_filter}",  # nosec B608 - table and optional column are validated identifiers; values are placeholders
            lookup_params,
        )
        if row is None:
            raise LookupError("business version not found")
        if row["status"] != "DRAFT":
            raise ValueError("only draft business versions can be approved")
        if row["created_by"] == approver:
            raise ValueError("business version requires a distinct approver")
        update_params = [approver, tenant_id, version_id]
        if parent_id is not None:
            update_params.append(parent_id)
        self._execute(
            f"UPDATE {table} SET status='ACTIVE', approved_by={p} WHERE tenant_id={p} AND id={p}{parent_filter} AND status='DRAFT'",  # nosec B608 - table and optional column are validated identifiers; values are placeholders
            update_params,
        )

    def create_subscription(self, item: Subscription) -> Subscription:
        self._insert(
            "subscription",
            [
                "id",
                "tenant_id",
                "contract_id",
                "contract_version_id",
                "service_plan_id",
                "status",
                "start_at",
                "end_at",
                "monthly_price",
                "currency",
                "recurring",
                "mrr_eligible",
                "revenue_treatment",
                "data_classification",
                "created_at",
            ],
            [
                item.id,
                item.tenant_id,
                item.contract_id,
                item.contract_version_id,
                item.service_plan_id,
                item.status,
                item.start_at,
                item.end_at,
                item.monthly_price,
                item.currency,
                item.recurring,
                item.mrr_eligible,
                item.revenue_treatment.value,
                item.classification.value,
                now_utc(),
            ],
        )
        return item

    def calculate_mrr(self, tenant_id: str, customer_id: str) -> dict[str, Any]:
        p = self.placeholder
        rows = self._execute(
            f"SELECT id, monthly_price, currency FROM subscription WHERE tenant_id={p} AND contract_id IN (SELECT id FROM customer_contract WHERE tenant_id={p} AND customer_id={p}) AND status='ACTIVE' AND recurring={p} AND mrr_eligible={p} AND revenue_treatment='RIBEIRA_RECURRING'",  # nosec B608 - only placeholders are interpolated
            [tenant_id, tenant_id, customer_id, True, True],
        ).fetchall()
        missing = []
        total = Decimal("0")
        components = []
        for row in rows:
            value = self._decimal(row["monthly_price"])
            if value is None:
                missing.append(str(row["id"]))
            else:
                total += value
                components.append(
                    {
                        "subscription_id": str(row["id"]),
                        "amount": value,
                        "currency": row["currency"],
                    }
                )
        return {
            "result": None if missing else money(total),
            "currency": "BRL",
            "classification": CommercialClassification.CALCULATED
            if not missing
            else CommercialClassification.UNKNOWN,
            "components": components,
            "missing_data": [f"subscription:{item}:monthly_price" for item in missing],
            "warnings": ["only active recurring Ribeira revenue is included"],
        }

    def create_asset(self, item: Asset) -> Asset:
        self._insert(
            "asset",
            [
                "id",
                "tenant_id",
                "asset_type",
                "name",
                "serial_number",
                "status",
                "property_id",
                "site_id",
                "data_classification",
                "created_at",
            ],
            [
                item.id,
                item.tenant_id,
                item.asset_type,
                item.name,
                item.serial_number,
                item.status,
                item.property_id,
                item.site_id,
                item.classification.value,
                now_utc(),
            ],
        )
        return item

    def create_asset_ownership(self, item: AssetOwnership) -> AssetOwnership:
        self._insert(
            "asset_ownership",
            [
                "id",
                "tenant_id",
                "asset_id",
                "ownership_kind",
                "customer_id",
                "purchased_by",
                "maintained_by",
                "replacement_responsibility",
                "risk_bearer",
                "valid_from",
                "valid_until",
                "acquisition_document",
                "data_classification",
                "created_at",
            ],
            [
                item.id,
                item.tenant_id,
                item.asset_id,
                item.ownership_kind.value,
                item.customer_id,
                item.purchased_by,
                item.maintained_by,
                item.replacement_responsibility,
                item.risk_bearer,
                item.valid_from,
                item.valid_until,
                item.acquisition_document,
                item.classification.value,
                now_utc(),
            ],
        )
        return item

    def create_installation_project(
        self, item: InstallationProject
    ) -> InstallationProject:
        self._insert(
            "installation_project",
            [
                "id",
                "tenant_id",
                "customer_id",
                "property_id",
                "name",
                "status",
                "technical_provider_type",
                "customer_total_project_cost",
                "currency",
                "ribeira_revenue_treatment",
                "data_classification",
                "created_at",
            ],
            [
                item.id,
                item.tenant_id,
                item.customer_id,
                item.property_id,
                item.name,
                item.status,
                item.technical_provider_type,
                item.customer_total_project_cost,
                item.currency,
                item.revenue_treatment.value,
                item.classification.value,
                now_utc(),
            ],
        )
        return item

    def create_capex_item(self, item: CapexItem) -> CapexItem:
        self._insert(
            "capex_item",
            [
                "id",
                "tenant_id",
                "project_id",
                "asset_id",
                "description",
                "amount",
                "currency",
                "capex_classification",
                "ownership_kind",
                "purchased_by",
                "source",
                "data_classification",
                "created_at",
            ],
            [
                item.id,
                item.tenant_id,
                item.project_id,
                item.asset_id,
                item.description,
                item.amount,
                item.currency,
                item.capex_classification.value,
                item.ownership_kind.value,
                item.purchased_by,
                item.source,
                item.classification.value,
                now_utc(),
            ],
        )
        return item

    def create_pass_through_item(self, item: PassThroughItem) -> PassThroughItem:
        self._insert(
            "pass_through_item",
            [
                "id",
                "tenant_id",
                "project_id",
                "customer_id",
                "description",
                "amount",
                "currency",
                "supplier",
                "document_reference",
                "paid_at",
                "data_classification",
                "created_at",
            ],
            [
                item.id,
                item.tenant_id,
                item.project_id,
                item.customer_id,
                item.description,
                item.amount,
                item.currency,
                item.supplier,
                item.document_reference,
                item.paid_at,
                item.classification.value,
                now_utc(),
            ],
        )
        return item

    def create_pricing_policy(self, item: PricingPolicy) -> PricingPolicy:
        self._insert(
            "pricing_policy",
            ["id", "tenant_id", "name", "scope", "status", "created_by", "created_at"],
            [
                item.id,
                item.tenant_id,
                item.name,
                item.scope,
                item.status,
                item.created_by,
                now_utc(),
            ],
        )
        return item

    def create_pricing_policy_version(
        self, item: PricingPolicyVersion
    ) -> PricingPolicyVersion:
        self._insert(
            "pricing_policy_version",
            [
                "id",
                "tenant_id",
                "pricing_policy_id",
                "version",
                "status",
                "lower_threshold",
                "lower_rate",
                "lower_minimum",
                "upper_rate",
                "upper_minimum",
                "currency",
                "valid_from",
                "valid_until",
                "created_by",
                "approved_by",
                "data_classification",
                "source",
                "created_at",
            ],
            [
                item.id,
                item.tenant_id,
                item.policy_id,
                item.version,
                item.status,
                item.lower_threshold,
                item.lower_rate,
                item.lower_minimum,
                item.upper_rate,
                item.upper_minimum,
                item.currency,
                item.valid_from,
                item.valid_until,
                item.created_by,
                item.approved_by,
                item.classification.value,
                item.source,
                now_utc(),
            ],
        )
        return item

    def get_pricing_policy_version(
        self, tenant_id: str, policy_id: str, version: int | None = None
    ) -> PricingPolicyVersion | None:
        p = self.placeholder
        condition = f"tenant_id={p} AND pricing_policy_id={p} AND status='ACTIVE'"
        params: list[Any] = [tenant_id, policy_id]
        if version is not None:
            condition += f" AND version={p}"
            params.append(version)
        if self.postgres:
            condition += " AND valid_from <= now() AND (valid_until IS NULL OR now() < valid_until)"
        rows = self._execute(
            f"SELECT * FROM pricing_policy_version WHERE {condition} ORDER BY version DESC",  # nosec B608 - condition contains only internal SQL fragments and placeholders
            params,
        ).fetchall()
        row = next(
            (
                candidate
                for candidate in rows
                if self.postgres
                or self._active_window(
                    candidate["valid_from"], candidate["valid_until"], now_utc()
                )
            ),
            None,
        )
        if row is None:
            return None
        return PricingPolicyVersion(
            str(row["id"]),
            str(row["tenant_id"]),
            str(row["pricing_policy_id"]),
            int(row["version"]),
            row["status"],
            Decimal(str(row["lower_threshold"])),
            Decimal(str(row["lower_rate"])),
            Decimal(str(row["lower_minimum"])),
            Decimal(str(row["upper_rate"])),
            Decimal(str(row["upper_minimum"])),
            row["currency"],
            self._timestamp(row["valid_from"]) or "",
            self._timestamp(row["valid_until"]),
            row["created_by"],
            row["approved_by"],
            self._classification(row["data_classification"]),
            row["source"],
        )

    def create_capacity_policy(
        self, item: OperationalCapacityPolicy
    ) -> OperationalCapacityPolicy:
        self._insert(
            "operational_capacity_policy",
            [
                "id",
                "tenant_id",
                "scope",
                "capacity_type",
                "value",
                "unit",
                "effective_from",
                "effective_until",
                "status",
                "created_by",
                "approved_by",
                "source",
                "data_classification",
                "created_at",
            ],
            [
                item.id,
                item.tenant_id,
                item.scope,
                item.capacity_type,
                item.value,
                item.unit,
                item.effective_from,
                item.effective_until,
                item.status,
                item.created_by,
                item.approved_by,
                item.source,
                item.classification.value,
                now_utc(),
            ],
        )
        return item

    def create_commercial_rule(
        self,
        rule_id: str,
        tenant_id: str,
        name: str,
        authority: str,
        status: str,
        created_by: str,
    ) -> str:
        self._insert(
            "commercial_rule",
            [
                "id",
                "tenant_id",
                "name",
                "authority",
                "status",
                "created_by",
                "created_at",
            ],
            [rule_id, tenant_id, name, authority, status, created_by, now_utc()],
        )
        return rule_id

    def create_commercial_rule_version(
        self,
        version_id: str,
        tenant_id: str,
        rule_id: str,
        version: int,
        condition: dict[str, Any],
        action: dict[str, Any],
        status: str,
        valid_from: str,
        valid_until: str | None,
        created_by: str,
        approved_by: str | None,
        classification: CommercialClassification,
    ) -> str:
        self._insert(
            "commercial_rule_version",
            [
                "id",
                "tenant_id",
                "commercial_rule_id",
                "version",
                "condition",
                "action",
                "status",
                "valid_from",
                "valid_until",
                "created_by",
                "approved_by",
                "data_classification",
                "created_at",
            ],
            [
                version_id,
                tenant_id,
                rule_id,
                version,
                self._json(condition),
                self._json(action),
                status,
                valid_from,
                valid_until,
                created_by,
                approved_by,
                classification.value,
                now_utc(),
            ],
        )
        return version_id

    def get_commercial_rule_version(
        self, tenant_id: str, rule_id: str, version: int | None = None
    ) -> dict[str, Any] | None:
        p = self.placeholder
        condition = f"tenant_id={p} AND commercial_rule_id={p} AND status='ACTIVE'"
        params: list[Any] = [tenant_id, rule_id]
        if version is not None:
            condition += f" AND version={p}"
            params.append(version)
        if self.postgres:
            condition += " AND valid_from <= now() AND (valid_until IS NULL OR now() < valid_until)"
        rows = self._execute(
            f"SELECT * FROM commercial_rule_version WHERE {condition} ORDER BY version DESC",  # nosec B608 - condition contains only internal SQL fragments and placeholders
            params,
        ).fetchall()
        row = next(
            (
                candidate
                for candidate in rows
                if self.postgres
                or self._active_window(
                    candidate["valid_from"], candidate["valid_until"], now_utc()
                )
            ),
            None,
        )
        if row is None:
            return None
        return {
            "id": str(row["id"]),
            "rule_id": str(row["commercial_rule_id"]),
            "version": int(row["version"]),
            "condition": json.loads(row["condition"]),
            "action": json.loads(row["action"]),
            "classification": row["data_classification"],
        }

    def evidence_exists(self, tenant_id: str, evidence_id: str) -> bool:
        p = self.placeholder
        return (
            self._one(
                f"SELECT 1 FROM evidence WHERE tenant_id={p} AND id={p}",  # nosec B608 - only placeholders are interpolated
                [tenant_id, evidence_id],
            )
            is not None
        )

    def create_scoring_model(
        self, model_id: str, tenant_id: str, name: str, status: str, created_by: str
    ) -> str:
        self._insert(
            "prospect_scoring_model",
            ["id", "tenant_id", "name", "status", "created_by", "created_at"],
            [model_id, tenant_id, name, status, created_by, now_utc()],
        )
        return model_id

    def active_capacity_policy(
        self, tenant_id: str, capacity_type: str, at: str
    ) -> OperationalCapacityPolicy | None:
        p = self.placeholder
        condition = f"tenant_id={p} AND capacity_type={p} AND status='ACTIVE'"
        params: list[Any] = [tenant_id, capacity_type]
        if self.postgres:
            condition += " AND effective_from <= %s AND (effective_until IS NULL OR %s < effective_until)"
            params.extend([at, at])
        rows = self._execute(
            f"SELECT * FROM operational_capacity_policy WHERE {condition} ORDER BY effective_from DESC",  # nosec B608 - condition contains only internal SQL fragments and placeholders
            params,
        ).fetchall()
        row = next(
            (
                candidate
                for candidate in rows
                if self.postgres
                or self._active_window(
                    candidate["effective_from"], candidate["effective_until"], at
                )
            ),
            None,
        )
        if row is None:
            return None
        return OperationalCapacityPolicy(
            str(row["id"]),
            str(row["tenant_id"]),
            row["scope"],
            row["capacity_type"],
            Decimal(str(row["value"])),
            row["unit"],
            self._timestamp(row["effective_from"]) or "",
            self._timestamp(row["effective_until"]),
            row["status"],
            row["created_by"],
            row["approved_by"],
            row["source"],
            self._classification(row["data_classification"]),
        )

    def create_opportunity(self, item: CommercialOpportunity) -> CommercialOpportunity:
        self._insert(
            "commercial_opportunity",
            [
                "id",
                "tenant_id",
                "customer_id",
                "property_id",
                "opportunity_type",
                "status",
                "classification",
                "score",
                "evidence_ids",
                "rule_id",
                "rule_version",
                "estimated_value",
                "estimated_value_classification",
                "created_at",
                "closed_at",
                "outcome",
            ],
            [
                item.id,
                item.tenant_id,
                item.customer_id,
                item.property_id,
                item.opportunity_type,
                item.status.value,
                item.classification.value,
                item.score,
                self._json(item.evidence_ids),
                item.rule_id,
                item.rule_version,
                item.estimated_value,
                item.estimated_value_classification.value,
                item.created_at or now_utc(),
                item.closed_at,
                item.outcome,
            ],
        )
        return item

    def create_opportunity_evidence(
        self, tenant_id: str, opportunity_id: str, evidence_id: str, role: str
    ) -> str:
        item_id = new_id()
        self._insert(
            "opportunity_evidence",
            ["id", "tenant_id", "opportunity_id", "evidence_id", "role", "created_at"],
            [item_id, tenant_id, opportunity_id, evidence_id, role, now_utc()],
        )
        return item_id

    def create_scoring_model_version(
        self, item: ProspectScoringModelVersion
    ) -> ProspectScoringModelVersion:
        self._insert(
            "prospect_scoring_model_version",
            [
                "id",
                "tenant_id",
                "model_id",
                "version",
                "status",
                "unknown_policy",
                "valid_from",
                "valid_until",
                "created_by",
                "approved_by",
                "data_classification",
                "created_at",
            ],
            [
                item.id,
                item.tenant_id,
                item.model_id,
                item.version,
                item.status,
                item.unknown_policy,
                item.valid_from,
                item.valid_until,
                item.created_by,
                item.approved_by,
                CommercialClassification.CONFIRMED.value,
                now_utc(),
            ],
        )
        return item

    def create_scoring_factor(
        self, item: ProspectScoringFactor
    ) -> ProspectScoringFactor:
        self._insert(
            "prospect_scoring_factor",
            [
                "id",
                "tenant_id",
                "model_version_id",
                "factor_key",
                "description",
                "condition",
                "points",
                "unknown_policy",
                "status",
                "created_at",
            ],
            [
                item.id,
                item.tenant_id,
                item.model_version_id,
                item.factor_key,
                item.description,
                self._json(item.condition),
                item.points,
                item.unknown_policy,
                item.status,
                now_utc(),
            ],
        )
        return item

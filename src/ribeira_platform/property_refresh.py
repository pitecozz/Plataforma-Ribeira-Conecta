"""Durable, tenant-isolated property data refresh orchestration.

This module deliberately schedules catalogue, ingest and processing separately
from a customer click.  It never changes a property boundary: provider output
is contextual evidence only.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from .geospatial import SatelliteSearchRequest, SceneSelectionPolicy
from .models import new_id, now_utc


DEFAULT_PROVIDER = "COPERNICUS_CDSE"
DEFAULT_COLLECTION = "sentinel-2-l2a"
DEFAULT_FREQUENCY_SECONDS = 12 * 60 * 60
DEFAULT_WINDOW_DAYS = 90


class PropertyRefreshService:
    """Schedules the supported Sentinel-2 automatic pipeline per property."""

    def __init__(self, application: Any) -> None:
        self.application = application

    @property
    def _postgres(self) -> bool:
        return self.application.store.__class__.__name__ == "PostgresStore"

    @property
    def _p(self) -> str:
        return "%s" if self._postgres else "?"

    @staticmethod
    def _has_cdse_asset_credentials() -> bool:
        return bool(os.getenv("CDSE_S3_ACCESS_KEY") and os.getenv("CDSE_S3_SECRET_KEY"))

    def register_property(
        self,
        tenant_id: str,
        property_id: str,
        *,
        actor: str,
        platform_admin: bool = False,
    ) -> dict[str, Any]:
        """Create the initial policy and exactly one initial backfill run.

        Called only after a persisted property already has an approved geometry.
        The stable initial key makes retries/restarts safe.
        """
        now = now_utc()
        p = self._p
        with self.application.store.tenant_transaction(tenant_id, platform_admin):
            self.application.store.connection.execute(
                f"""INSERT INTO property_refresh_policy
                (tenant_id,property_id,provider_id,collection_id,enabled,frequency_seconds,
                 search_window_days,cloud_cover_limit,auto_process,next_search_at,retry_count,
                 status,created_at,updated_at)
                VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p},{p},0,'QUEUED',{p},{p})
                ON CONFLICT (tenant_id,property_id,provider_id,collection_id) DO NOTHING""",  # nosec B608
                [
                    tenant_id,
                    property_id,
                    DEFAULT_PROVIDER,
                    DEFAULT_COLLECTION,
                    True,
                    DEFAULT_FREQUENCY_SECONDS,
                    DEFAULT_WINDOW_DAYS,
                    "50",
                    True,
                    now,
                    now,
                    now,
                ],
            )
            run = self._enqueue_in_transaction(
                tenant_id, property_id, "INITIAL_PROPERTY_CONTEXT_REFRESH", now
            )
            self.application.store.audit(
                tenant_id,
                actor,
                "PROPERTY_REFRESH_POLICY_REGISTERED",
                "property",
                property_id,
                {
                    "provider": DEFAULT_PROVIDER,
                    "collection": DEFAULT_COLLECTION,
                    "initial_refresh_run_id": str(run["id"]),
                },
                new_id(),
                now,
            )
            return dict(run)

    def bootstrap_existing(self, *, actor: str, apply: bool) -> list[dict[str, str]]:
        """Find pre-policy approved AOIs without touching their geometry.

        This private migration companion is intentionally explicit: existing
        customer properties receive the same initial run only when the operator
        invokes the CLI with ``--apply``. New imports are automatic.
        """
        p = self._p
        with self.application.store.tenant_transaction(None, True):
            rows = self.application.store.connection.execute(
                f"""SELECT p.tenant_id,p.id FROM property p
                WHERE p.geometry IS NOT NULL AND NOT EXISTS (
                  SELECT 1 FROM property_refresh_policy r
                  WHERE r.tenant_id=p.tenant_id AND r.property_id=p.id
                    AND r.provider_id={p} AND r.collection_id={p}
                ) ORDER BY p.tenant_id,p.id""",  # nosec B608
                [DEFAULT_PROVIDER, DEFAULT_COLLECTION],
            ).fetchall()
        candidates = [
            {"tenant_id": str(row["tenant_id"]), "property_id": str(row["id"])}
            for row in rows
        ]
        if apply:
            for candidate in candidates:
                self.register_property(
                    candidate["tenant_id"],
                    candidate["property_id"],
                    actor=actor,
                    platform_admin=True,
                )
        return candidates

    def enqueue_manual(
        self,
        tenant_id: str,
        property_id: str,
        *,
        actor: str,
        platform_admin: bool = False,
    ) -> dict[str, Any]:
        now = now_utc()
        with self.application.store.tenant_transaction(tenant_id, platform_admin):
            if self._policy(tenant_id, property_id) is None:
                raise LookupError("property automatic refresh policy not found")
            # A time-bucket keeps a double click/retry from producing duplicate work.
            run = self._enqueue_in_transaction(
                tenant_id, property_id, "MANUAL", now, bucket_seconds=300
            )
            self.application.store.audit(
                tenant_id,
                actor,
                "PROPERTY_REFRESH_MANUALLY_REQUESTED",
                "property_refresh_run",
                str(run["id"]),
                {"property_id": property_id},
                new_id(),
                now,
            )
            return dict(run)

    def _enqueue_in_transaction(
        self,
        tenant_id: str,
        property_id: str,
        trigger: str,
        now: str,
        bucket_seconds: int | None = None,
    ) -> Any:
        p = self._p
        bucket = (
            "initial"
            if bucket_seconds is None
            else str(int(datetime.now(UTC).timestamp()) // bucket_seconds)
        )
        key = f"property-refresh:v1:{property_id}:{DEFAULT_PROVIDER}:{DEFAULT_COLLECTION}:{trigger}:{bucket}"
        self.application.store.connection.execute(
            f"""INSERT INTO property_refresh_run
            (id,tenant_id,property_id,provider_id,collection_id,trigger_type,status,idempotency_key,
             scheduled_at,next_attempt_at,attempt,max_attempts,created_at,updated_at)
            VALUES ({p},{p},{p},{p},{p},{p},'QUEUED',{p},{p},{p},0,3,{p},{p})
            ON CONFLICT (tenant_id,idempotency_key) DO NOTHING""",  # nosec B608
            [
                new_id(),
                tenant_id,
                property_id,
                DEFAULT_PROVIDER,
                DEFAULT_COLLECTION,
                trigger,
                key,
                now,
                now,
                now,
                now,
            ],
        )
        return self.application.store.connection.execute(
            f"SELECT * FROM property_refresh_run WHERE tenant_id={p} AND idempotency_key={p}",  # nosec B608
            [tenant_id, key],
        ).fetchone()

    def _policy(self, tenant_id: str, property_id: str) -> Any:
        p = self._p
        return self.application.store.connection.execute(
            f"""SELECT * FROM property_refresh_policy WHERE tenant_id={p} AND property_id={p}
            AND provider_id={p} AND collection_id={p}""",  # nosec B608
            [tenant_id, property_id, DEFAULT_PROVIDER, DEFAULT_COLLECTION],
        ).fetchone()

    def status(
        self, tenant_id: str, property_id: str, *, platform_admin: bool = False
    ) -> dict[str, Any] | None:
        with self.application.store.tenant_transaction(tenant_id, platform_admin):
            item = self._policy(tenant_id, property_id)
            return dict(item) if item else None

    def claim_due(self, *, worker_id: str) -> dict[str, Any] | None:
        """Atomically lease one due run; Postgres uses SKIP LOCKED for workers."""
        now = now_utc()
        with self.application.store.tenant_transaction(None, True):
            stale_seconds = min(
                max(int(os.getenv("RIBEIRA_PROPERTY_REFRESH_STALE_SECONDS", "60")), 60),
                86400,
            )
            if self._postgres:
                self.application.store.connection.execute(
                    """UPDATE property_refresh_run SET status='RETRYABLE', next_attempt_at=now(),
                    failure_code='STALE_WORKER_LEASE', failure_reason='STALE_WORKER_LEASE', updated_at=now()
                    WHERE status='RUNNING' AND started_at < now() - (%s * interval '1 second')""",
                    [stale_seconds],
                )
            if self._postgres:
                row = self.application.store.connection.execute(
                    """WITH candidate AS (
                      SELECT id FROM property_refresh_run
                      WHERE status IN ('QUEUED','RETRYABLE') AND next_attempt_at <= now()
                      ORDER BY next_attempt_at, scheduled_at FOR UPDATE SKIP LOCKED LIMIT 1
                    ) UPDATE property_refresh_run r SET status='RUNNING', started_at=now(),
                    attempt=r.attempt+1, updated_at=now()
                    FROM candidate WHERE r.id=candidate.id RETURNING r.*"""
                ).fetchone()
            else:
                row = self.application.store.connection.execute(
                    """SELECT * FROM property_refresh_run WHERE status IN ('QUEUED','RETRYABLE')
                    AND next_attempt_at <= ? ORDER BY next_attempt_at,scheduled_at LIMIT 1""",
                    [now],
                ).fetchone()
                if row:
                    self.application.store.connection.execute(
                        "UPDATE property_refresh_run SET status='RUNNING',started_at=?,attempt=attempt+1,updated_at=? WHERE id=?",
                        [now, now, row["id"]],
                    )
                    row = self.application.store.connection.execute(
                        "SELECT * FROM property_refresh_run WHERE id=?", [row["id"]]
                    ).fetchone()
            if row is None:
                return None
            result = dict(row)
            # psycopg returns uuid objects; tenant_transaction configures a
            # PostgreSQL text setting and therefore must receive text, never a
            # UUID parameter. Keep this conversion at the queue boundary.
            for key in (
                "id",
                "tenant_id",
                "property_id",
                "search_id",
                "processing_job_id",
            ):
                if result.get(key) is not None:
                    result[key] = str(result[key])
            return result

    def run_one(self, *, worker_id: str = "property-refresh") -> dict[str, Any] | None:
        run = self.claim_due(worker_id=worker_id)
        if run is None:
            return None
        tenant_id, property_id = run["tenant_id"], run["property_id"]
        now = datetime.now(UTC)
        try:
            with self.application.store.tenant_transaction(tenant_id, True):
                policy = self._policy(tenant_id, property_id)
            if policy is None or not bool(policy["enabled"]):
                return self._finish(
                    run, "BLOCKED", "REFRESH_POLICY_DISABLED", None, None
                )
            request = SatelliteSearchRequest(
                property_id=property_id,
                collection_id=policy["collection_id"],
                datetime_start=(
                    now - timedelta(days=int(policy["search_window_days"]))
                ).isoformat(),
                datetime_end=now.isoformat(),
                selection_policy=SceneSelectionPolicy(
                    cloud_cover_limit=Decimal(str(policy["cloud_cover_limit"]))
                    if policy["cloud_cover_limit"] is not None
                    else None,
                    max_candidates=100,
                ),
            )
            result = self.application.geospatial.search_satellite(
                tenant_id, request, actor=f"worker:{worker_id}", platform_admin=True
            )
            latest_available = result.scenes[0].id if result.scenes else None
            latest_usable = result.search.selected_scene_id
            if latest_usable and bool(policy["auto_process"]):
                if not self._has_cdse_asset_credentials():
                    return self._finish(
                        run,
                        "BLOCKED",
                        "CDSE_S3_CREDENTIALS_REQUIRED",
                        result.search.id,
                        None,
                        latest_available=latest_available,
                        latest_usable=latest_usable,
                    )
                job = self.application.geospatial.create_ndvi_job(
                    tenant_id,
                    property_id,
                    result.search.id,
                    actor=f"worker:{worker_id}",
                    platform_admin=True,
                )
                return self._finish(
                    run,
                    "SUCCEEDED",
                    None,
                    result.search.id,
                    job.id,
                    latest_available=latest_available,
                    latest_usable=latest_usable,
                )
            return self._finish(
                run,
                "SUCCEEDED",
                None,
                result.search.id,
                None,
                latest_available=latest_available,
                latest_usable=latest_usable,
            )
        except Exception as exc:
            # Provider exception payloads may contain sensitive endpoint details.
            state = (
                "RETRYABLE"
                if int(run["attempt"]) < int(run["max_attempts"])
                else "FAILED"
            )
            return self._finish(run, state, type(exc).__name__, None, None)

    def _finish(
        self,
        run: dict[str, Any],
        status: str,
        code: str | None,
        search_id: str | None,
        job_id: str | None,
        *,
        latest_available: str | None = None,
        latest_usable: str | None = None,
    ) -> dict[str, Any]:
        now = now_utc()
        p = self._p
        delay = min(3600, 60 * (2 ** max(0, int(run["attempt"]) - 1)))
        next_attempt = (
            (datetime.now(UTC) + timedelta(seconds=delay)).isoformat()
            if status == "RETRYABLE"
            else None
        )
        with self.application.store.tenant_transaction(run["tenant_id"], True):
            self.application.store.connection.execute(
                f"""UPDATE property_refresh_run SET status={p},finished_at={p},next_attempt_at={p},search_id={p},processing_job_id={p},failure_code={p},failure_reason={p},updated_at={p} WHERE tenant_id={p} AND id={p}""",  # nosec B608
                [
                    status,
                    now,
                    next_attempt,
                    search_id,
                    job_id,
                    code,
                    code,
                    now,
                    run["tenant_id"],
                    run["id"],
                ],
            )
            frequency = self._policy(run["tenant_id"], run["property_id"])[
                "frequency_seconds"
            ]
            self.application.store.connection.execute(
                f"""UPDATE property_refresh_policy SET last_search_at={p},last_success_at=CASE WHEN {p}='SUCCEEDED' THEN {p} ELSE last_success_at END,
                last_failure_at=CASE WHEN {p} IN ('RETRYABLE','FAILED','BLOCKED') THEN {p} ELSE last_failure_at END,
                next_search_at={p},latest_available_scene_id=COALESCE({p},latest_available_scene_id),
                latest_usable_scene_id=COALESCE({p},latest_usable_scene_id),retry_count=CASE WHEN {p}='RETRYABLE' THEN retry_count+1 ELSE retry_count END,
                status={p},failure_code={p},failure_reason={p},updated_at={p}
                WHERE tenant_id={p} AND property_id={p} AND provider_id={p} AND collection_id={p}""",  # nosec B608
                [
                    now,
                    status,
                    now,
                    status,
                    now,
                    (datetime.now(UTC) + timedelta(seconds=int(frequency))).isoformat(),
                    latest_available,
                    latest_usable,
                    status,
                    status,
                    code,
                    code,
                    now,
                    run["tenant_id"],
                    run["property_id"],
                    run["provider_id"],
                    run["collection_id"],
                ],
            )
            # A terminal execution schedules the next bounded provider check.
            # Retries instead keep their own leased run/backoff; this avoids
            # parallel duplicate searches for the same property/provider.
            if status in {"SUCCEEDED", "BLOCKED", "FAILED"}:
                self._enqueue_in_transaction(
                    run["tenant_id"],
                    run["property_id"],
                    "SCHEDULED",
                    (datetime.now(UTC) + timedelta(seconds=int(frequency))).isoformat(),
                    bucket_seconds=int(frequency),
                )
            self.application.store.audit(
                run["tenant_id"],
                "worker:property-refresh",
                "PROPERTY_REFRESH_FINISHED",
                "property_refresh_run",
                str(run["id"]),
                {
                    "status": status,
                    "failure_code": code,
                    "search_id": str(search_id) if search_id else None,
                    "processing_job_id": str(job_id) if job_id else None,
                },
                new_id(),
                now,
            )
            row = self.application.store.connection.execute(
                f"SELECT * FROM property_refresh_run WHERE tenant_id={p} AND id={p}",
                [run["tenant_id"], run["id"]],
            ).fetchone()
            return dict(row)

    def record_processed_scene(
        self,
        tenant_id: str,
        property_id: str,
        scene_id: str,
        *,
        platform_admin: bool = False,
    ) -> None:
        """Advance freshness only after a derived product has actually persisted."""
        p = self._p
        with self.application.store.tenant_transaction(tenant_id, platform_admin):
            self.application.store.connection.execute(
                f"""UPDATE property_refresh_policy SET latest_processed_scene_id={p},
                status='SUCCEEDED', failure_code=NULL, failure_reason=NULL, updated_at={p}
                WHERE tenant_id={p} AND property_id={p} AND provider_id={p} AND collection_id={p}""",  # nosec B608
                [
                    scene_id,
                    now_utc(),
                    tenant_id,
                    property_id,
                    DEFAULT_PROVIDER,
                    DEFAULT_COLLECTION,
                ],
            )

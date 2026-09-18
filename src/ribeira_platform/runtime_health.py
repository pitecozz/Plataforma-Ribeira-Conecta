"""Objective private-runtime liveness, readiness, and degraded checks."""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .postgres import PostgresStore


def _http(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:  # nosec B310 - fixed loopback URLs
            return response.status == 200
    except urllib.error.URLError:
        return False


def check(target: str) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    if target in {"all", "api"}:
        checks["api_liveness"] = _http("http://127.0.0.1:8080/health/live")
        checks["api_readiness"] = _http("http://127.0.0.1:8080/health/ready")
    if target in {"all", "frontend"}:
        checks["frontend_liveness"] = _http("http://127.0.0.1:5173/health/live")
        checks["frontend_readiness"] = _http("http://127.0.0.1:5173/health/ready")
    if target in {"all", "worker"}:
        checks["worker_metrics"] = _http("http://127.0.0.1:9109/metrics")
    queue: dict[str, int] | None = None
    if target in {"all", "database", "queue"}:
        dsn = os.getenv("RIBEIRA_DATABASE_URL")
        if dsn:
            try:
                store = PostgresStore(dsn)
                try:
                    checks["database_readiness"] = store.ready()
                    with store.tenant_transaction(None, platform_admin=True):
                        rows = store.connection.execute(
                            "SELECT status, COUNT(*) AS count "
                            "FROM processing_job GROUP BY status"
                        ).fetchall()
                    queue = {str(row["status"]): int(row["count"]) for row in rows}
                    checks["queue_readiness"] = True
                finally:
                    store.close()
            except Exception:
                checks["database_readiness"] = False
                checks["queue_readiness"] = False
        else:
            checks["database_readiness"] = False
            checks["queue_readiness"] = False
    if target in {"all", "storage"}:
        root = Path(os.getenv("RIBEIRA_OBJECT_STORAGE_ROOT", ".local/object-storage"))
        checks["object_storage_ready"] = root.is_dir() and os.access(
            root, os.R_OK | os.W_OK
        )
    status = "ready" if all(checks.values()) else "degraded"
    result: dict[str, Any] = {"status": status, "checks": checks}
    if queue is not None:
        result["queue"] = queue
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Ribeira private runtime health")
    parser.add_argument(
        "target",
        choices=("all", "api", "frontend", "worker", "database", "queue", "storage"),
    )
    parser.add_argument("--wait-seconds", type=int, default=0)
    args = parser.parse_args()
    deadline = time.monotonic() + args.wait_seconds
    while True:
        result = check(args.target)
        if result["status"] == "ready" or time.monotonic() >= deadline:
            print(json.dumps(result, sort_keys=True))
            raise SystemExit(0 if result["status"] == "ready" else 1)
        time.sleep(1)


if __name__ == "__main__":
    main()

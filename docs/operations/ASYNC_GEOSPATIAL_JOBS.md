# Asynchronous geospatial jobs runbook

## Start a private worker

Apply migrations first, then run the worker only on a private host/network:

```bash
PYTHONPATH=src .venv/bin/python -m ribeira_platform.geospatial_worker
```

For a supervised health check or a one-job execution:

```bash
PYTHONPATH=src .venv/bin/python -m ribeira_platform.geospatial_worker --once
```

`RIBEIRA_GEOSPATIAL_WORKER_ID` identifies the worker in transition evidence.
`RIBEIRA_GEOSPATIAL_STALE_AFTER_SECONDS` defaults to 3600 and must be at least
60 seconds. `RIBEIRA_GEOSPATIAL_MAX_ATTEMPTS` defaults to 3 (range 1–10).

## State and retry semantics

`QUEUED → RUNNING → SUCCEEDED` is the successful path. `RUNNING` jobs with an
expired heartbeat return to `QUEUED` if attempts remain; otherwise they become
`FAILED/WORKER_HEARTBEAT_EXPIRED`. Processing errors remain `FAILED` with a
sanitized code. Credential blocking is `BLOCKED/BLOCKED_BY_CREDENTIAL` and
requires remediation before an explicit retry. A retry preserves job ID,
idempotency key, provenance, and transition evidence; it never manufactures a
product.

Do not manually alter `processing_job` status or `schema_migrations`. Inspect
the tenant-scoped job and `processing_job_transition` history instead. A worker
crash is recovered by the heartbeat policy, and concurrent workers are safe
because claims and terminal updates require the current lease.

## Observability and security

Prometheus metrics are exposed by the private worker only at
`http://127.0.0.1:9109/metrics` by default. Set
`RIBEIRA_GEOSPATIAL_METRICS_PORT=0` to disable it, or select another loopback
port for another worker. The metrics are:

- `ribeira_geospatial_queued_jobs`, `ribeira_geospatial_running_jobs`
- `ribeira_geospatial_jobs_total`
- `ribeira_geospatial_job_duration_seconds`
- `ribeira_geospatial_job_retries_total`
- `ribeira_geospatial_stale_jobs_total`

Logs include technical job and tenant IDs only. Provider credentials, raw
exception messages, and object-store secrets must not be logged or returned to
the frontend. The worker uses server-side credentials and runs with PostgreSQL
RLS context; its endpoint is never publicly exposed.

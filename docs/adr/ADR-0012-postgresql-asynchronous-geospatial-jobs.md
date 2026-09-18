# ADR-0012: PostgreSQL-backed asynchronous geospatial jobs

## Status

Accepted.

## Context

NDVI, quality-masked NDVI and temporal-delta processing can download inputs and
run Rasterio/GDAL. Running that work in an HTTP request keeps a client
connection open and leaves no durable lease, retry history, or crash recovery.
PostgreSQL and RLS are already the authoritative persistence boundary.

## Decision

Use `processing_job` as a PostgreSQL-backed durable queue. A private worker
atomically claims an eligible `QUEUED` row with `FOR UPDATE SKIP LOCKED`, then
processes it outside the HTTP request. `processing_job_transition` is append-only
tenant-scoped audit evidence for every status change.

The worker holds a lease (`claimed_by`, `claimed_at`, `heartbeat_at`). A separate
private PostgreSQL connection refreshes the heartbeat for long work. Expired
leases return to `QUEUED` while attempts remain, or become `FAILED` with
`WORKER_HEARTBEAT_EXPIRED`. The existing logical idempotency key is unique per
tenant, so retry reuses the same job rather than creating an untracked duplicate.

`BLOCKED` is reserved for a persisted, actionable prerequisite failure such as
`BLOCKED_BY_CREDENTIAL`; it is not a success or a synthetic product.

## Alternatives considered

| Option | Assessment |
| --- | --- |
| PostgreSQL queue | Reuses required infrastructure, transactional state/RLS, and `SKIP LOCKED`; selected. |
| Redis + worker | Adds a durable service, credential, backup, monitoring, and reconciliation boundary without a demonstrated throughput need. |
| Celery/Kafka/Kubernetes | Adds scheduling, broker, operational and failure-mode complexity beyond this single-VPS phase. |

## Consequences

The API returns `202 Accepted` after durable enqueue and the Farm 360 client
polls with bounded exponential backoff. Workers are private processes and must
be supervised by the host. This is intentionally not a public queue endpoint or
a WebSocket system.

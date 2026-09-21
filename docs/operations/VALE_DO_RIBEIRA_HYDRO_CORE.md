# Vale do Ribeira hydrology core

Phase 1P.1 stores public hydrology reference data globally, once per provider.
It does not duplicate stations, observations, reservoir operations or climate
context for each tenant. Property exposure, risk assessment, alerts, actions,
commercial impact and Farm360 interpretation remain future tenant-scoped data.

`VALE_DO_RIBEIRA` is seeded as an administrative discovery scope only. Its
geometry is intentionally `UNKNOWN` and null until an official, verifiable
boundary is available; the platform does not draw a substitute polygon.

## Provider states

- ANA HidroWebService: `AUTH_REQUIRED`. The modern official API inventory and
  telemetry endpoints are represented structurally. A future private
  `~/.config/ribeira/ana-hidroweb.env` must be owned by the runtime user with
  mode `0600`; no placeholder file or credential is created by the platform.
- CEMADEN PED: `AUTH_REQUIRED` until the official JWT is supplied out of band.
- SAISP: `SOURCE_UNAVAILABLE` for automation. The public portal remains a
  manual evidence reference until a stable structured public contract is
  verified. No browser automation or HTML scraping is used.
- COPEL: `PUBLIC_OFFICIAL_SOURCE`. The adapter accepts only an explicit,
  official Capivari gate-opening statement with a machine-readable publication
  timestamp. It never derives a discharge value from qualitative prose.
- NOAA CPC: `PUBLIC_OFFICIAL_SOURCE`. ENSO records are climate context, not a
  flood cause or a risk score.

## Provenance and quality

Every global observation/event carries provider, source reference, fetch time,
parser version/provenance and classification. `hydro_hypothesis_evidence`
links hypotheses to global facts because the existing `evidence` table is
correctly tenant-scoped and cannot be reused without forging tenant ownership.

The core marks duplicate keys, missing station, invalid coordinate/numeric
value, unsupported unit, future/stale timestamp, negative rainfall and
provider conflict. It never converts units, replaces missing data with zero or
interpolates river stage. Aggregates and stage deltas are pure, non-persistent
calculations until real observations exist.

## Private ingestion

After migration 019 is applied, run the private, idempotent command with the
existing runtime database configuration:

```bash
PYTHONPATH=src .venv/bin/python -m ribeira_platform.hydrology_ingest
```

The command fetches only fixed official HTTPS URLs, bounds response size and
prints provider states and counts only. It does not print provider page bodies,
credentials or identifiers. The situation API is read-only and tenant
authorized at:

`GET /v1/tenants/{tenant_id}/vale-do-ribeira/situation`

It requires the existing `geospatial:read` permission. This preserves normal
OIDC membership/RBAC enforcement while exposing shared global reference facts.

## Operational WIS2 reconciliation and September 2026 evidence window

Phase 1P.4 adds a private `systemd --user` timer,
`ribeira-wis2-reconcile.timer`. It runs the bounded WIS2 HTTP reconciler every
30 minutes with a randomized delay and a three-hour overlap. The one-shot
service uses a runtime lock, has no listener, follows only the official HTTPS
OGC API, retries only bounded transient failures, and relies on provider-record
and observation uniqueness for idempotency.

`hydrology_operational --historical-backfill` uses the same normalizer but
queries only already verified WIGOS stations for the September 2026 evidence
window. Each run records sanitized received/inserted/duplicate/invalid/error,
duration and report-lag metrics in `hydro_ingestion_run`. Failed runs degrade
source health but retain prior observations.

`VALE_RIBEIRA_FLOOD_2026_09` is a factual evidence window, not a causal
assertion. Its timeline links real rainfall observations, calculated complete-
coverage rainfall peaks, existing Copel operation evidence, and NOAA climate
context in separate lanes. It does not state that rain, reservoir operations,
or ENSO caused flooding. ANA remains `AUTH_REQUIRED_PENDING_PROVIDER`; the
private `~/.config/ribeira/ana-hidroweb.env` is not created until official
credentials arrive.

# Ribeira private production runtime foundation

This is a private, loopback-only runtime. It does not authorize public
exposure, changes to SSH/UFW, PostgreSQL publishing, or a public worker.

## Architecture decision

Use `systemd --user` services for API, geospatial worker, and the static
frontend. PostgreSQL/PostGIS remains the existing Compose service bound to
`127.0.0.1:55432`. No Redis, Celery, Kafka, Kubernetes, Nginx, or Caddy is
introduced. Nginx/Caddy are absent on this VPS; a small Python static server is
acceptable only because this phase binds it to loopback and serves static build
files, not application data.

## Configuration

The actual configuration is outside Git:

```bash
RIBEIRA_DATABASE_URL="..." ops/runtime/provision-runtime-config.sh
chmod 600 ~/.config/ribeira/runtime.env ~/.config/ribeira/cdse.env
```

`runtime.env` contains server-side database/auth configuration. `cdse.env`
contains only CDSE credentials. Neither is copied into the frontend or a Git
backup. The versioned `ops/runtime/runtime.env.example` is documentation only.

Use `RIBEIRA_ENV=development` only for the current controlled private
validation runtime, `test` for isolated test databases/doubles, and `production`
for a deployed private service runtime. Templates for each mode live under
`ops/runtime/`. Production requires real JWT/OIDC configuration; do not place a
development bearer token in `frontend/dist`.

## Install, start, stop, restart, status

```bash
ops/runtime/install-user-services.sh
systemctl --user start ribeira-api ribeira-geospatial-worker ribeira-frontend
systemctl --user stop ribeira-frontend ribeira-geospatial-worker ribeira-api
systemctl --user restart ribeira-api
systemctl --user status ribeira-api ribeira-geospatial-worker ribeira-frontend
journalctl --user -u ribeira-api -u ribeira-geospatial-worker -u ribeira-frontend -f
```

The services run as the `ribeira` user. They use explicit working directory and
virtualenv paths, journal stdout/stderr, restart on failure, and receive
`SIGTERM` for graceful shutdown. The worker completes its current bounded job
when possible; an interrupted lease is recovered by heartbeat/stale semantics.

For boot persistence, an administrator must enable user lingering once:

```bash
loginctl enable-linger ribeira
```

Then verify with `loginctl show-user ribeira -p Linger`. Do not reboot merely to
test this phase.

## Health and queue

```bash
set -a; . ~/.config/ribeira/runtime.env; set +a
PYTHONPATH=src .venv/bin/python -m ribeira_platform.runtime_health all
curl http://127.0.0.1:8080/health/live
curl http://127.0.0.1:8080/health/ready
curl http://127.0.0.1:9109/metrics
```

`runtime_health` also reports durable queue counts without exposing tenant or
credential data. Liveness means the API process is running. Readiness requires PostgreSQL.
`SOURCE_UNAVAILABLE` from an external provider is a job/data-quality condition,
not an API liveness failure. `runtime_health` reports `degraded` for unavailable
private dependencies without serializing credentials.

## Frontend

Build static assets before starting the frontend service:

```bash
cd frontend
npm run build
```

`ribeira-frontend.service` serves `frontend/dist` on `127.0.0.1:5173`; it never
runs Vite. A real interactive OIDC/session flow is still required before a
private production frontend can authenticate users without a browser-delivered
development token.

## Object storage

`LocalObjectStorage` is currently
`/home/ribeira/Plataforma-Ribeira-Conecta/.local/object-storage`, owned by
`ribeira` and ignored by Git. Its location is explicit in the protected runtime
configuration; do not silently point a service at a new empty root. Keys are
tenant-scoped opaque paths. COG writes use a same-directory
temporary file, `fsync`, and `os.replace`, so a restart cannot expose a partial
destination. Local disk remains a single-host durability risk; do not migrate
to S3/MinIO automatically in this phase.

## Backup, restore, rollback

```bash
backup_dir="$(ops/backup/backup-runtime.sh)"
ops/backup/verify-backup-restore.sh "$backup_dir"
```

The backup reads only the nonsecret object-root setting from protected runtime
configuration; it contains a PostgreSQL custom archive, object-storage tarball,
checksums, and the nonsecret configuration example. The verification script
checks checksums and object archive, restores PostgreSQL to a temporary
database, compares migration counts, verifies every persisted local derived
product reference is present in the archived objects, and drops that temporary
database. It never backs up `~/.config/ribeira/*.env`. The backup uses the PostgreSQL
superuser inside the private Compose container because the application role is
correctly constrained by RLS.

Migration rollback remains controlled through the migration runner. Do not
manually alter `schema_migrations`; do not rollback migrations with audit/data
loss implications on the live validation database.

## Controlled service recovery

With no critical job intentionally in flight, run:

```bash
ops/runtime/verify-service-recovery.sh
```

It validates all private dependencies, gracefully restarts the worker and API,
then validates them again. Queue concurrency, retries, and stale lease recovery
are covered by the PostgreSQL integration tests with explicitly classified
doubles; the runtime probe never starts a CDSE download merely to test a restart.

## Emergency stop

```bash
systemctl --user stop ribeira-geospatial-worker
```

This stops new claims. Running work receives graceful termination; stale lease
recovery preserves a durable job state. Do not delete `processing_job`, COGs,
or database volumes as an emergency action.

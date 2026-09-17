# Desenvolvimento local

## Caminho reproduzível

Requisitos: Python 3.12, Docker Compose e Git.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock
.venv/bin/pip install -e .
docker compose up -d postgres
RIBEIRA_MIGRATION_DATABASE_URL=postgresql://ribeira_admin:ribeira_admin_dev_only@127.0.0.1:55432/ribeira_dev \
  .venv/bin/python -m ribeira_platform.migrations upgrade
RIBEIRA_TEST_DATABASE_URL=postgresql://ribeira_app:ribeira_app_dev_only@127.0.0.1:55432/ribeira_dev \
  .venv/bin/python -m unittest discover -s tests -v
```

O compose é somente desenvolvimento. As credenciais do arquivo são dev-only e
não devem ser reutilizadas. Em produção, migrations usam credencial separada e
a aplicação usa apenas a role não proprietária.

## CDSE external verification

The normal suite does not require internet. To run the real official catalogue
contract test explicitly, use:

```bash
RIBEIRA_CDSE_EXTERNAL_TEST=1 PYTHONPATH=src \
  .venv/bin/python -m unittest tests.integration.test_cdse_external -v
```

This discovers metadata only. It does not download the provider's `s3://`
assets and does not create a customer/property record.

## CDSE authenticated asset verification

Configure only through the runtime environment or an external secret store;
never commit the values. The adapter reads `CDSE_S3_ACCESS_KEY` and
`CDSE_S3_SECRET_KEY`. Optional non-secret settings are `CDSE_S3_ENDPOINT` and
`CDSE_S3_BUCKET`; the implementation accepts only the official CDSE HTTPS
endpoints and bucket `eodata`. Limits include
`CDSE_S3_MAX_OBJECT_BYTES`, `CDSE_S3_MAX_JOB_BYTES`,
`CDSE_S3_MAX_ASSETS_PER_JOB`, `CDSE_S3_TIMEOUT_SECONDS` and
`CDSE_S3_MAX_RETRIES`.

Run the explicit test only in an isolated test environment:

```bash
RIBEIRA_CDSE_S3_EXTERNAL_TEST=1 \
  PYTHONPATH=src .venv/bin/python -m unittest \
  tests.integration.test_cdse_s3_external -v
```

Without credentials, the test skips with `CDSE S3 credentials are not
configured` and no NDVI is claimed. In the application, the corresponding
processing job ends as `BLOCKED_BY_CREDENTIAL` and records no derived raster.
When it runs, it requires local SHA-256 checksums for RED and NIR, an output
SHA-256 checksum, valid NDVI pixels in `[-1, 1]`, and structural COG validation
of the persisted output. It does not persist a PostgreSQL evidence chain; that
is covered separately by the explicitly synthetic PostgreSQL/PostGIS test.

## API

```bash
RIBEIRA_DATABASE_URL=postgresql://ribeira_app:ribeira_app_dev_only@127.0.0.1:55432/ribeira_dev \
  RIBEIRA_AUTH_MODE=development \
  RIBEIRA_DEV_AUTH_TOKEN=dev-only-token \
  .venv/bin/python -m ribeira_platform.api
```

O provider de desenvolvimento é deliberadamente explícito e não é uma
autenticação de produção. Produção deve configurar JWT/OIDC com issuer,
audience e chave pública/JWKS; MFA/passkeys ficam no Identity Provider.

## Farm 360 frontend

The Farm 360 frontend is intentionally loopback-only for local development:

```bash
cd frontend
npm install
VITE_RIBEIRA_API_URL=http://127.0.0.1:8080 \
VITE_RIBEIRA_TENANT_ID=<tenant-id> \
VITE_RIBEIRA_PROPERTY_ID=<property-id> \
VITE_RIBEIRA_ACCESS_TOKEN=<session-token> npm run dev
```

Use SSH port forwarding for remote development; do not bind Vite to `0.0.0.0`
or disable UFW. `VITE_RIBEIRA_ACCESS_TOKEN` is an existing browser session token,
never a CDSE S3 credential. The COG itself remains server-side and is served as
authorized PNG tiles. See `docs/geospatial/FARM_360_V1.md` for the tile and
evidence flow.

## Comandos úteis

- `make db-up`, `make db-migrate`, `make test`, `make security`;
- `... -m ribeira_platform.migrations rollback 1` para rollback controlado;
- `RIBEIRA_ENV=development RIBEIRA_ALLOW_CLEAN=1 ... migrations clean` somente
  para reset local.

Se Docker não estiver disponível, a suíte unitária continua executável com
SQLite. Os testes de integração só são considerados válidos quando
`RIBEIRA_TEST_DATABASE_URL` aponta para PostgreSQL/PostGIS real.

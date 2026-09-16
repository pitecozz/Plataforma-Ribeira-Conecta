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

## Comandos úteis

- `make db-up`, `make db-migrate`, `make test`, `make security`;
- `... -m ribeira_platform.migrations rollback 1` para rollback controlado;
- `RIBEIRA_ENV=development RIBEIRA_ALLOW_CLEAN=1 ... migrations clean` somente
  para reset local.

Se Docker não estiver disponível, a suíte unitária continua executável com
SQLite. Os testes de integração só são considerados válidos quando
`RIBEIRA_TEST_DATABASE_URL` aponta para PostgreSQL/PostGIS real.

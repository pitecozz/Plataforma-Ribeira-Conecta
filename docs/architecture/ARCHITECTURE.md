# Arquitetura inicial

## Decisão

Começar com modular monolith + workers/adapters, extraindo serviços apenas quando
escala, ownership, segurança ou processamento justificarem. O caminho de
produção desta fase é PostgreSQL/PostGIS com uma role de aplicação não
proprietária; SQLite permanece somente para testes rápidos e desenvolvimento
explicitamente local.

```text
FastAPI `/v1` + OpenAPI
        |
authn/authz + request context
        |
Application service
  /       |        \
Source  Evidence  Decision
adapters Engine    Engine
        |           |
PostgreSQL/PostGIS  alert/action/audit
        |
Object Storage + STAC + workers (próximas fases)
```

## Boundaries

- `sources.py`: provider interface e normalização; não conhece regras de negócio.
- `storage.py`: persistência local de teste; não cria conclusões.
- `postgres.py`: adapter de produção, transações e contexto RLS; não cria conclusões.
- `engine.py`: evidence e decision engine determinísticos.
- `service.py`: orquestração do workflow e idempotência.
- `api.py`: transporte, validação, autenticação, autorização e limites HTTP.
- `migrations.py`: upgrade/rollback com checksum e advisory lock.

## Geospatial

PostGIS é a persistência de produção, com geometria, GIST, migrations reais e
RLS `USING`/`WITH CHECK` com `FORCE ROW LEVEL SECURITY`. COG/STAC/object storage
e workers raster permanecem como próxima vertical slice. SQLite não é
apresentado como substituto espacial.

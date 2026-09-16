# Arquitetura inicial

## Decisão

Começar com modular monolith + workers/adapters, extraindo serviços apenas quando
escala, ownership, segurança ou processamento justificarem. O núcleo atual é
dependency-free para permitir validação local no workspace sem Docker,
PostgreSQL ou credenciais externas.

```text
HTTP API (dev surface)
        |
Application service
  /       |        \
Source  Evidence  Decision
adapters Engine    Engine
        |           |
  SQLite local   alert/action/audit
        |
PostgreSQL/PostGIS + Object Storage + STAC (produção futura)
```

## Boundaries

- `sources.py`: provider interface e normalização; não conhece regras de negócio.
- `storage.py`: persistência e tenant boundary; não cria conclusões.
- `engine.py`: evidence e decision engine determinísticos.
- `service.py`: orquestração do workflow.
- `api.py`: transporte; autenticação real deve ficar no gateway/middleware.

## Geospatial

PostGIS é o alvo de produção, com geometria e GIST. COG/STAC/object storage e
workers raster permanecem como próxima vertical slice. SQLite não é apresentado
como substituto espacial.

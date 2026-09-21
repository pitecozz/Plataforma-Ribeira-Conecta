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
  /       |          |          \
Source  Evidence  Decision   Business
adapters Engine    Engine     Application
        |           |          |
PostgreSQL/PostGIS  alert/action/audit
        |
Object Storage + STAC + workers (próximas fases)
```

Catálogo, acesso a dados, processamento e imagens de visualização são portas
distintas. Missões como Sentinel-1, Sentinel-2, Landsat 8 e Landsat 9 não ficam
acopladas a um único fornecedor; CDSE, Google Earth Engine, USGS/NASA, JRC e
outros provedores são adapters independentes, com seleção explícita,
proveniência e regras de compatibilidade. Google Earth de visualização não é
contrato de fonte nem evidência. Veja
`docs/geospatial/PROVIDER_ABSTRACTION.md`.

## Boundaries

- `sources.py`: provider interface e normalização; não conhece regras de negócio.
- `storage.py`: persistência local de teste; não cria conclusões.
- `postgres.py`: adapter de produção, transações e contexto RLS; não cria conclusões.
- `engine.py`: evidence e decision engine determinísticos.
- `business.py`: aggregates e engines puros de pricing, capacidade, regras
  comerciais e prospect score.
- `business_service.py`: casos de uso comerciais e invariantes de aprovação,
  ownership, MRR e evidência.
- `business_repository.py`: adapter de persistência comercial; não contém
  autorização HTTP nem fórmulas de negócio.
- `service.py`: orquestração do workflow e idempotência.
- `api.py`: transporte, validação, autenticação, autorização e limites HTTP.
- `migrations.py`: upgrade/rollback com checksum e advisory lock.

## Geospatial

PostGIS é a persistência de produção, com geometria, GIST, migrations reais e
RLS `USING`/`WITH CHECK` com `FORCE ROW LEVEL SECURITY`. COG/STAC/object storage
e workers raster permanecem como próxima vertical slice. SQLite não é
apresentado como substituto espacial.

## Direção operacional

O mapa e o dashboard são consumidores do domínio, não o próprio produto. A
evolução segue `ativo -> dado -> contexto -> regra -> decisão -> ação ->
resultado`, com proveniência e resultado/fechamento persistidos em cada salto.
A fundação compartilhada é o Digital Twin espacial e multi-tenant de
ativos/contexto; Connect, Agro, IoT, Energy, Security, Prospect e Farm360 devem
compor essa fundação em vez de criar silos. A priorização atual, gates de
evidência e dependências estão em `docs/CODEX_AUTONOMOUS_DELIVERY.md`.

## Agro, solo e telemetria de campo

Soil Intelligence reutiliza ativos/contexto do Digital Twin, PostGIS/RLS,
proveniência de provedores e o motor de regras; não cria uma base paralela de
fazendas, sensores ou eventos de inundação. Áreas desenhadas para análise e
zonas de manejo são geometrias derivadas e versionadas, não limites legais.
Dados remotos/modelados, sensores observados e laudos laboratoriais permanecem
classes de evidência distintas. A futura entrada MQTT/HTTPS fica atrás de
adapters autenticados e tenant-bound, e qualquer estimativa virtual preserva
modelo, incerteza e calibração. Veja `docs/agro/` e `docs/iot/FIELD_TELEMETRY.md`.

## Business boundaries

O catálogo não assume que todo produto está ativo. `customer_contract` registra
links externos sem converter o pagamento do provedor em receita Ribeira;
`asset_ownership` diferencia Ribeira, cliente, terceiro, leasing, pass-through e
desconhecido; `pricing_policy_version` e `operational_capacity_policy` são
configurações vigentes e auditáveis. O limite de referência de 10 instalações
por mês não é constante de código.

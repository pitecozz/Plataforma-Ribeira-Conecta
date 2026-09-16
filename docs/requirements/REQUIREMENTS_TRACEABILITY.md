# Requirements Traceability

`IMPLEMENTED` significa código e teste executados nesta fase; `PREPARED`
significa contrato/abstração sem integração externa real; `GAP` significa que
não foi implementado.

| Requisito | Source | Domain | Component | Database | API/Event | Rule | Test | Status |
|---|---|---|---|---|---|---|---|---|
| Isolamento por tenant | Prompt §§57-58 | Tenant boundary | `AuthorizationPolicy`, `PostgresStore` | RLS + FKs compostas | tenant da identidade, não URL | default deny | integração RLS/read/write/insert | IMPLEMENTED |
| Migrations reais | Prompt §§3-4 | persistence | `migrations.py` | `schema_migrations` + checksum | CLI upgrade/rollback | advisory lock | clean/upgrade/rollback executados | IMPLEMENTED |
| Propriedade com geometria/CRS | Prompt §37 | Property | service/Postgres adapter | PostGIS geometry + GIST | `POST /v1/.../properties` | classificação | PostGIS round trip | IMPLEMENTED |
| Adapter sem fallback fabricado | Prompt §§41,73-74 | Source/Observation | provider adapter | observation + DQ event | ingestion route | `SOURCE_UNAVAILABLE` | source unavailable/invalid payload | IMPLEMENTED |
| Proveniência Evidence First | Prompt §§3-5,83-84 | Evidence | `EvidenceEngine` | source/observation/evidence | evidence IDs | sem imputation | evidence chain | IMPLEMENTED |
| Regra versionada | Prompt §§30-33 | Rule | `DecisionEngine` | `rule_definition` | create/active/evaluate | validade + aprovação | trigger/validity/SoD | IMPLEMENTED |
| Conclusão inconclusiva | Prompt §§8-10,95 | Decision | decision engine | decision limitations/missing | evaluate | unknown/conflict | missing/conflict | IMPLEMENTED |
| Idempotência | Prompt §17 | ingestion | application service | unique idempotency indexes | ingestion | event identity | duplicate ingestion | IMPLEMENTED |
| Auditoria | Prompt §§10-11,89,91 | Audit | store + middleware | `audit_log` | request/correlation IDs | input/version refs | audit and API headers | IMPLEMENTED |
| IAM/RBAC/JWT | Prompt §§58-62 | IAM | provider + policy | IAM schema | bearer auth | default deny | valid/invalid JWT and authorization | IMPLEMENTED/PREPARED |
| MFA/Passkeys | Prompt §11 | IAM | OIDC boundary | external IdP | claims/revocation contract | IdP policy | provider contract only | PREPARED |
| SSRF/provider registry | Prompt §§14-15 | Provider | network policy/registry | `provider_registry` | no generic fetch route | allowlist | private/metadata blocked | IMPLEMENTED |
| Data quality/time | Prompt §§20-22,64 | Quality | normalizer/time utils | quality flags/timestamps | validation errors | valid only | NULL/UNKNOWN/timezone | IMPLEMENTED |
| PostGIS/GIS foundation | Prompt §40 | Spatial | Postgres adapter | geometry/SRID/GIST | property route | CRS validation | real PostGIS | IMPLEMENTED |
| Official providers beyond CDSE | Blueprint fase 1 | Provider | future adapters | future datasets | provider-specific | future external tests | GAP |
| IoT/MQTT/LoRaWAN | Blueprint fase 2 | Telemetry | future | device/measurement future | event bus future | replay rules | future | GAP |
| Banana Intelligence | Prompt §§34-35 | Agronomy | future | agronomic observations | future | no diagnosis from satellite | future | GAP |
| Domínio comercial e catálogo | Fase 1B §§4-6, 30 | Customer, Catalog, Delivery | `business.py`, `business_service.py` | migration 006 | operation-oriented `/v1` endpoints | configuração sobre hardcode | `tests/test_business.py`, PG business integration | IMPLEMENTED |
| Ownership e pass-through | Fase 1B §§6-9, 40 | Asset, Finance | `AssetOwnership`, `PassThroughItem` | `asset_ownership`, `pass_through_item` | asset ownership endpoint | ownership explícito; sem inferência | unit + PG/RLS integration | IMPLEMENTED |
| Contratos versionados e MRR | Fase 1B §§10-11, 31-32 | Contract, Subscription | `BusinessApplication`, repository | `customer_contract`, `contract_version`, `subscription` | contract/catalog/MRR endpoints | vigência + tratamento de receita | business domain tests | IMPLEMENTED |
| Pricing transparente em Decimal | Fase 1B §§14-18, 41-42 | Pricing | `PricingEngine` | `pricing_policy_version` numeric | simulate price endpoint | `INCOMPLETE_PRICING`; monotonicidade | Decimal/monotonicity/missing input tests | IMPLEMENTED |
| Capacity Gate versionado | Fase 1B §§12-13, 43 | Capacity | `CapacityEngine` | `operational_capacity_policy` | capacity create/evaluate | sem expansão automática | boundary/gate tests | IMPLEMENTED |
| Opportunity Evidence First | Fase 1B §§23-29, 34 | Commercial Intelligence | `CommercialRuleEngine`, `BusinessApplication` | opportunity + evidence link | rule/qualification endpoints | `UNKNOWN` não pontua como ausência | unknown/evidence/RLS tests | IMPLEMENTED |
| Prospect Score configurável | Fase 1B §§27-29 | Prospect | scoring model/factor domain | `prospect_scoring_*` | application operation prepared | unknown policy explícita | engine tests | IMPLEMENTED/PREPARED |
| IAM comercial e segregação | Fase 1B §§36-39 | Authorization/Audit | central `AuthorizationPolicy`, audit | audit + tenant RLS | `commercial:*`, `pricing:*`, `contract:*`, `asset:*` | default deny + approver distinto | auth/API + PG tests | IMPLEMENTED |

| CDSE official STAC provider | Fase 1C §§1-6 | Geospatial provider | `CopernicusStacAdapter`, `ProviderRegistry` | provider metadata | provider adapter | official endpoint/collection metadata | controlled external contract test | IMPLEMENTED |
| Sentinel-2 L2A discovery and provenance | Fase 1C §§8-16, 26 | Satellite scene/asset | geospatial application/repository | scene/asset/search/candidate | search API | raw response/checksum/source | geospatial + external tests | IMPLEMENTED |
| CRS/AOI validation | Fase 1C §§7-10 | Spatial AOI | `GeometryService` | PostGIS geometry 4326 | search operation | no silent repair/default CRS | invalid geometry/PostGIS tests | IMPLEMENTED |
| Explicit scene selection | Fase 1C §§32-34, 61 | Scene policy | `SceneSelectionPolicy` | persisted candidate criteria | search result | versioned policy; no fallback | selection/unit tests | IMPLEMENTED |
| NDVI derived raster | Fase 1C §§17-31, 43-46 | Derived product | `NdviProcessor`, controlled job | derived product + COG reference | NDVI job/provenance API | formula/version/nodata | local raster tests | IMPLEMENTED/ASSET GAP |
| Tenant isolation for geospatial data | Fase 1C §§39-40 | Tenant-scoped geospatial | RLS + repository | forced RLS/FKs | tenant-scoped endpoints | default deny | real Postgres geospatial RLS | IMPLEMENTED |
| External asset download | Fase 1C §§15, 37, 63-64 | Asset processing | future authenticated adapter | object storage future | processing job | allowlist/credentials | no fabricated fallback | GAP |
| Banana diagnosis / Prospect consumption | Fase 1C §§68-69 | out of scope | not implemented | not applicable | not exposed | prohibited in phase | negative scope review | GAP/BLOCKED BY SCOPE |

## Vertical slice rastreado

`POST /v1/.../properties` cria a propriedade; source registra a origem; ingestão
normaliza e deduplica; observação válida gera evidência; evaluate aplica uma
regra ativa válida; decisão pode criar alerta/ação e cada etapa relevante deixa
auditoria. A versão Postgres é exercitada por `tests/integration`.

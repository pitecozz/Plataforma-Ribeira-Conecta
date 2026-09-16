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
| Official providers | Blueprint fase 1 | Provider | adapters future | datasets/STAC future | contracts future | provider-specific | no real calls | GAP |
| IoT/MQTT/LoRaWAN | Blueprint fase 2 | Telemetry | future | device/measurement future | event bus future | replay rules | future | GAP |
| Banana Intelligence | Prompt §§34-35 | Agronomy | future | agronomic observations | future | no diagnosis from satellite | future | GAP |

## Vertical slice rastreado

`POST /v1/.../properties` cria a propriedade; source registra a origem; ingestão
normaliza e deduplica; observação válida gera evidência; evaluate aplica uma
regra ativa válida; decisão pode criar alerta/ação e cada etapa relevante deixa
auditoria. A versão Postgres é exercitada por `tests/integration`.

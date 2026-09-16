# Requirements Traceability

Legenda de status: `IMPLEMENTED` significa coberto pelo slice atual; `PARTIAL`
significa contrato/documentação preparada, mas falta integração de produção;
`GAP` significa ainda não implementado.

| Requisito | Source | Domain | Component | Database | API/Event | Rule | Test | Status |
|---|---|---|---|---|---|---|---|---|
| Isolamento por tenant | Prompt §§57-58, blueprint `multi_tenant` | Tenant boundary | `SQLiteStore`, RLS PostGIS | `tenant_id` em entidades | rotas escopadas por tenant | política de acesso | `test_tenant_isolation` | IMPLEMENTED local / PARTIAL prod |
| Propriedade com geometria e CRS | Prompt §37, blueprint `digital_twin` | Property | `RibeiraApplication` | `property.geometry` PostGIS | `POST .../properties` | classificação manual | `test_property_creation` | IMPLEMENTED |
| Adapter sem inventar fallback | Prompt §§41,73-74 | Source/Observation | `HttpJsonSourceAdapter` | `source`, `observation`, DQ event | ingestion route | `SOURCE_UNAVAILABLE` | `test_source_unavailable` | IMPLEMENTED |
| Proveniência e classificação epistemológica | Prompt §§3-5,83-84 | Evidence | `EvidenceEngine` | `evidence` | decisão referencia evidence IDs | sem imputation | `test_evidence_chain` | IMPLEMENTED |
| Regra versionada | Prompt §§30-33 | Rule | `DecisionEngine` | `rule_definition` | `POST .../rules` | operador/limiar configurável | `test_rule_trigger` | IMPLEMENTED local |
| Conclusão inconclusiva | Prompt §§8-10,95 | Decision | `DecisionEngine` | `decision` | `.../evaluate` | missing/conflict states | `test_missing_data` | IMPLEMENTED |
| Conflito entre fontes | Prompt §7 | Data quality | `DecisionEngine` | `data_quality_event`, `decision.conflicts` | evaluate | não escolher silenciosamente | `test_conflicting_sources` | IMPLEMENTED |
| Alerta e próxima ação | Prompt §§56,83-84 | Action/Alert | `DecisionEngine` | `alert`, `action` | resposta da avaliação | responsável/prazo nulos se desconhecidos | `test_rule_trigger` | IMPLEMENTED |
| Auditoria de decisão | Prompt §§10-11,89,91 | Audit | `SQLiteStore.audit` | `audit_log` | evento interno | rule/model/input refs | `test_audit` | IMPLEMENTED local |
| PostGIS e GIS | Prompt §40 | Spatial | SQL migration | geometry + GIST | futuro spatial API | CRS obrigatório | schema review | PARTIAL |
| RBAC/MFA/ABAC | Prompt §§58-62 | IAM | gateway futuro | user/role/permission futuros | auth middleware futuro | least privilege | security suite futura | GAP |
| Providers oficiais (CAR/SIGEF/satélite etc.) | Blueprint fase 1 | Provider | adapters futuros | datasets/STAC futuros | source version | contract tests futuros | GAP |
| IoT/MQTT/LoRaWAN | Blueprint fase 2 | Telemetry | adapters futuros | device/measurement futuros | event bus futuro | identity/replay rules | IoT suite futura | GAP |
| Banana Intelligence | Prompt §§34-35 | Agronomy | model/rules futuros | agronomic observations | alert workflows | no diagnosis from satellite | agronomy suite futura | GAP |

## Rastreabilidade do vertical slice

`POST /properties` cria a propriedade; `POST /sources` registra a origem;
`POST /ingestions/{source_id}` chama o adapter configurado; os dados válidos
viram `observation` e `evidence`; `POST /evaluate` executa exclusivamente uma
regra ativa; o resultado persiste `decision`, eventualmente `alert` e `action`,
e sempre grava `audit_log`.

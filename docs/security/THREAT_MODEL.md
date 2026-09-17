# Threat model — Fase 1A + Fase 1B

## Escopo

API FastAPI `/v1`, application service, PostgreSQL/PostGIS, RLS, adapters HTTP,
regras versionadas, evidência, decisões, alertas, ações e auditoria. IA,
MQTT, providers oficiais e frontend não estão habilitados nesta fase.

## Controles implementados e evidência

| Ameaça | Controle | Evidência/teste | Risco residual |
|---|---|---|---|
| Tenant breakout/IDOR | identidade + política default-deny; tenant derivado do contexto; RLS `USING`/`WITH CHECK`; `FORCE RLS`; FKs compostas | `tests/integration/test_postgres_integration.py` | credencial de DBA legítimo e dependência do segredo da role app |
| Cross-tenant reference | constraints compostas e trigger `enforce_evidence_reference_tenant` | inserts cross-tenant de observation/evidence/decision/alert/action | referências de novos domínios exigem novas constraints |
| JWT inválido | issuer/audience/exp/sub obrigatórios e assinatura JWT/OIDC | `tests/test_iam_and_ssrf.py`, API 401 | rotação/JWKS operacional e MFA dependem do IdP |
| Privilégio excessivo | RBAC central default-deny; permissões por role; SoD para aprovação de regra | testes de autorização e API | ABAC completo e membership persistido ainda não expostos no endpoint |
| Regra maliciosa | regra ativa exige aprovação; validade timezone-aware; aprovação distinta no API | testes de regra/validade | Rule Studio e workflow de aprovação completos são próximos passos |
| SSRF | somente HTTP(S), bloqueio de localhost/private/link-local/metadata, redirects desabilitados e provider allowlist | `tests/test_iam_and_ssrf.py` | DNS rebinding/egress proxy/WAF precisam controle de infraestrutura |
| Payload malformado | Pydantic extra-forbid, limite de body, content-length válido, DQ `INVALID_PAYLOAD` | `tests/test_api.py` e testes de adapter | rate limiting distribuído ainda é edge concern |
| Replay/duplicação | idempotency key determinística e unique index por tenant | teste de ingestion repetida | sem ingestão MQTT/device identity nesta fase |
| Fonte indisponível | `SOURCE_UNAVAILABLE`, evento de qualidade, nenhuma substituição fabricada | testes de source unavailable | retry/circuit breaker/provider observability avançados |
| SQL/injection | parâmetros psycopg/SQLite e tabela de count allowlisted | Bandit + suíte | auditoria de queries e proxy DB futuros |
| Segredos no código | `.env.example` somente dev; secret scan CI; role app separada | `detect-secrets` no CI | Secret Manager e rotação ainda pendentes |
| Auditoria insuficiente | actor/tenant/operação/recurso/payload/request/correlation IDs; sem token | schema, middleware e integration tests | append-only/imutabilidade/SIEM e retenção precisam plataforma |
| Supply chain | pins declarativos/lock, SCA com pip-audit, SAST, secret scan e SBOM | workflow CI | image/IaC scanning, DAST e pentest ainda pendentes |
| Dados falsos | classificação epistemológica, NULL/UNKNOWN preservados, sem fallback implícito | integrity/vertical-slice tests | cobertura de todos os futuros módulos ainda não existe |
| Fraude ou alteração de preço | Pricing Engine fora do controller, Decimal, política versionada e aprovação distinta | testes de pricing, SoD e auditoria de versão | ainda não há workflow de aprovação com membership persistido |
| Contrato histórico sobrescrito | `contract_version` com vigência e constraint de versão por tenant | testes de versão e schema PostgreSQL | endpoint de consulta histórica ainda é limitado |
| Ownership fraudulento | ownership explícito, temporal, auditado e tenant-scoped | testes de ownership/RLS; audit de alteração | validações de segregação de função para todos os papéis ainda dependem do IdP |
| Cross-tenant financeiro | RLS `USING`/`WITH CHECK`, FKs compostas nas entidades comerciais | `test_business_domain_is_persisted_and_rls_blocks_cross_tenant_references` | novos aggregates precisam seguir o mesmo padrão |
| Oportunidade comercial falsa | regra ternária, evidência obrigatória, UNKNOWN inconclusivo | `test_business_application_keeps_evidence_chain_and_mrr_rules` e PG RLS | não há ainda workflow de qualificação humana completo |
| Autoaprovação comercial | versões ativas de regra, preço, capacidade e contrato exigem aprovador distinto | testes de SoD em application service/API | identidade do aprovador ainda é claim/subject, não diretório persistido |

## Riscos residuais de produção

1. Docker Compose é uma reprodução local; não é um deployment de produção.
2. TLS termination, WAF, rate limiting distribuído, egress proxy, backup
   imutável, DR, SIEM, image/IaC scanning, DAST e pentest ainda precisam ser
   implantados no ambiente operacional.
3. O provider de autenticação de desenvolvimento é deliberadamente não
   produtivo. Produção exige IdP OIDC/JWT, MFA/passkeys, revogação e rotação de
   chaves.
4. CDSE STAC metadata discovery foi exercitado com consulta real e allowlist.
   Asset download autenticado ainda não foi configurado; nenhum raster CDSE é
   afirmado como baixado. CAR, Anatel e IoT continuam sem consulta real.

## Revisão pós-implementação

Esta revisão foi executada após a introdução do adapter Postgres, API, IAM,
SSRF policy, migrations e CI. Os controles acima têm código e testes associados;
os riscos residuais não foram marcados como resolvidos por documentação.

## Revisão pós-Fase 1C

| Ameaça geoespacial | Controle | Evidência/teste | Risco residual |
|---|---|---|---|
| Catálogo STAC malicioso | schema validation, bounded pages/response, no arbitrary href execution | CDSE adapter tests + external contract test | provider payload changes require contract review |
| SSRF via asset href | catalog and asset hosts are separately allowlisted; local processor accepts only `local://` | provider registry/network policy + raster tests | production downloader still to be implemented |
| Redirect/host pivot | redirects disabled and next links validated | provider adapter tests | DNS/egress controls remain infrastructure responsibility |
| Oversized geometry/raster/resource exhaustion | polygon validity, bounded candidates, response/object size, explicit jobs | geospatial unit tests | production quotas/queue isolation remain |
| Cross-tenant geospatial leak | tenant-scoped tables, composite FKs, forced RLS and application tenant context | `test_geospatial_postgres.py` | privileged DBA remains trusted |
| Cache/raw metadata poisoning | checksum and tenant-keyed raw references; no global scene dedup | repository/idempotency tests | immutable object storage is future operational control |
| False agronomic diagnosis | NDVI only classified `DERIVED`, limitations explicitly recorded | NDVI test and documentation | future agronomic models need separate validation |

## Revisão pós-Fase 1C.1 — acesso autenticado a assets

| Ameaça | Controle | Evidência/teste | Risco residual |
|---|---|---|---|
| Credential leakage | credential provider externo; exceções e resultados não carregam segredo; não há credenciais em logs/auditoria | `tests/test_cdse_s3.py::test_authentication_error_is_redacted`, secret scan | rotação e secret manager são responsabilidade operacional futura |
| Bucket confusion | parser aceita somente `s3://eodata/<key>` e endpoint não é derivado da URI | `test_reference_requires_exact_cdse_bucket_and_safe_key` | mudança de bucket oficial exige alteração de configuração revisada |
| SSRF via S3 URI | endpoint HTTPS exato e allowlistado; host da URI não escolhe rede | adapter + `NetworkPolicy` | egress enforcement/DNS rebinding continuam controles de infraestrutura |
| Malicious object/path traversal | object key validado, destino local gerado pelo sistema, `put_file` usa raiz controlada | adapter tests e object-storage safety tests | provider comprometido ainda pode enviar conteúdo raster malformado |
| Oversized raster/resource exhaustion | `HeadObject`, limite de streaming, limite por job/asset, número limitado de assets | `test_oversized_object_is_rejected_before_download` | limites precisam ser calibrados por observação real |
| Stale/invalid credentials | estados explícitos `BLOCKED_BY_CREDENTIAL` e `PROVIDER_AUTHENTICATION_FAILED`; sem fallback silencioso | adapter tests; external test opt-in | renovação operacional ainda depende do CDSE |
| Cache/tenant leak | chave local inclui tenant e asset; atualização de asset é tenant-scoped | repository/application tests | object storage compartilhado de produção exige política imutável e revisão |

## Revisão pós-Fase 1B

Foi incluída a migration `006_business_domain.sql`, executada em PostgreSQL
16 com PostGIS, incluindo RLS forçado para as tabelas comerciais e FKs
compostas para referências tenant-scoped. O teste de integração exercita
SELECT, UPDATE, DELETE e INSERT com referências cruzadas. A revisão não
considera integrações externas, score com pesos ativos, MFA de produção ou
imutabilidade física do audit log como concluídos nesta fase.

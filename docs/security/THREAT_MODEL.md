# Threat model — Fase 1A

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

## Riscos residuais de produção

1. Docker Compose é uma reprodução local; não é um deployment de produção.
2. TLS termination, WAF, rate limiting distribuído, egress proxy, backup
   imutável, DR, SIEM, image/IaC scanning, DAST e pentest ainda precisam ser
   implantados no ambiente operacional.
3. O provider de autenticação de desenvolvimento é deliberadamente não
   produtivo. Produção exige IdP OIDC/JWT, MFA/passkeys, revogação e rotação de
   chaves.
4. Os providers externos ainda são contratos/allowlist, sem consulta real ou
   licença. Nenhum dado de satélite, CAR, Anatel ou IoT é afirmado como obtido.

## Revisão pós-implementação

Esta revisão foi executada após a introdução do adapter Postgres, API, IAM,
SSRF policy, migrations e CI. Os controles acima têm código e testes associados;
os riscos residuais não foram marcados como resolvidos por documentação.

# Threat model inicial

## Escopo

Primeiro slice: API, persistência tenant-scoped, adapters HTTP, regras, evidência,
alertas e auditoria.

## Ameaças e controles atuais

| Ameaça | Impacto | Controle atual | Gap |
|---|---|---|---|
| Tenant breakout/IDOR | exposição de propriedade/telemetria | queries exigem `tenant_id`; schema RLS PostGIS | autenticação e testes de gateway |
| Fonte indisponível | decisão falsa | `SOURCE_UNAVAILABLE`, DQ event, sem fallback | retry/circuit breaker/observability |
| Payload malformado | corrupção | validação de campos e tipos | schema/size limits no gateway |
| Regra maliciosa ou sem aprovação | alerta indevido | regra ativa exige `approved_by`, versionamento | RBAC/SoD/Rule Studio |
| Prompt/RAG poisoning | conclusão falsa | IA não está habilitada no slice | grounding, ACL, prompt injection defense |
| SSRF via endpoint | acesso indevido à rede | endpoint é configuração explícita, sem auth no adapter | allowlist, egress proxy, URL policy |
| Replay/telemetria forjada | ação incorreta | nenhum MQTT no slice | device identity, nonce, mTLS, replay window |
| XSS/injection | comprometimento | API sem renderização HTML | gateway/WAF/headers/auth |
| Auditoria insuficiente | não repúdio perdido | decisão e ingestão auditadas | append-only/imutabilidade/SIEM |

## Gaps críticos antes de produção

1. MFA/passkeys, RBAC/ABAC e autorização por objeto.
2. Gateway com TLS, rate limit, WAF, allowlist de providers e limites de payload.
3. Secrets Manager e rotação; nenhuma credencial em código.
4. RLS validado em PostgreSQL sob role não proprietária.
5. SAST/SCA/secret scan/SBOM/DAST e threat-model review no CI.
6. Backups imutáveis, restauração testada e plano DR.

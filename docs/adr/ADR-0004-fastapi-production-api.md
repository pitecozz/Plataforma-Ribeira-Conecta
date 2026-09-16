# ADR-0004: FastAPI como superfície HTTP de produção

- Status: accepted
- Data: 2026-09-16

## Contexto

O bootstrap usava uma superfície HTTP mínima. A Fase 1A exige OpenAPI,
validação forte, middleware de request/correlation ID, health checks, limites e
tratamento de erro consistente.

## Decisão

Usar FastAPI/Pydantic como adapter HTTP sobre o application service. O domínio e
os ports não importam FastAPI. A autenticação é uma abstração de IdentityProvider
e a autorização fica em uma política central default-deny.

## Alternativas

Flask/WSGI e um servidor HTTP próprio foram considerados. Flask exigiria montar
manualmente o contrato OpenAPI/validação; o servidor próprio manteria o risco do
bootstrap e duplicaria controles. Nenhuma alternativa justificou o custo.

## Impacto e limites

O adapter oferece JWT/OIDC ou um provider de desenvolvimento explicitamente
marcado. MFA/passkeys continuam responsabilidade do Identity Provider. TLS,
WAF e rate limiting distribuído pertencem ao edge/gateway e não são simulados
pela API.

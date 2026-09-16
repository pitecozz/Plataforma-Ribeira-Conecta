# ADR-0005: RLS forçado e contexto transacional de tenant

- Status: accepted
- Data: 2026-09-16

## Decisão

Entidades tenant-owned usam PostgreSQL Row Level Security com `USING` e
`WITH CHECK`, e `FORCE ROW LEVEL SECURITY`. A role da aplicação é
`NOSUPERUSER`, não é owner e não possui bypass de RLS. O adapter só executa
operações tenant-scoped dentro de uma transação que define
`app.tenant_id`/`app.platform_admin` como configurações locais à transação.

Além do RLS, o backend valida que o tenant da URL/recurso coincide com a
identidade autenticada. FKs compostas e trigger de Evidence reforçam que UUID
conhecido não permite criar referências cross-tenant.

## Bootstrap e administração

Migrations rodam com uma role administrativa separada. Criação de tenant ocorre
em fluxo de platform admin; usuários comuns não escolhem tenant pelo body,
header ou query string. A exceção `platform_admin` é explícita, auditável e
restrita ao contexto de identidade.

## Risco residual

O valor de `app.platform_admin` é definido pelo backend e a proteção depende da
confidencialidade das credenciais da role da aplicação. Não há garantia contra
um administrador de banco legítimo; esse risco requer segregação operacional,
secrets manager e auditoria do ambiente de produção.

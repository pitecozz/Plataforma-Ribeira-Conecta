# Ribeira Conecta Intelligence Platform

Fundação inicial da plataforma operacional de inteligência da Ribeira Conecta.

O primeiro vertical slice implementado é:

```text
PROPRIEDADE -> FONTE -> INGESTÃO -> POSTURA DE DADOS -> EVIDÊNCIA
-> REGRA VERSIONADA -> CONCLUSÃO -> ALERTA -> AÇÃO -> AUDITORIA
```

## Estado atual

O workspace original estava vazio e não continha JSON, código, Git, banco,
testes ou integrações. O blueprint foi lido a partir de
`/home/pitequin/Downloads/ribeira_conecta_blueprint_completo.json` e sua
proveniência está registrada em `docs/requirements/BLUEPRINT_SOURCE.md`.

O núcleo não fabrica observações: sem endpoint configurado, o adaptador retorna
`SOURCE_UNAVAILABLE`, registra um evento de qualidade e produz conclusão
inconclusiva. Fixtures sintéticas existem somente nos testes e são marcadas como
`synthetic_data=true` no contrato de teste; nunca são usadas pelo servidor.

## Executar localmente

O caminho recomendado usa Docker Compose com PostgreSQL/PostGIS, migrations e
autenticação de desenvolvimento explicitamente marcada. SQLite continua
disponível apenas para testes rápidos. Veja o passo a passo em
`docs/operations/LOCAL_DEVELOPMENT.md`.

```bash
docker compose up -d postgres
RIBEIRA_MIGRATION_DATABASE_URL=postgresql://ribeira_admin:ribeira_admin_dev_only@127.0.0.1:55432/ribeira_dev \
  PYTHONPATH=src python3 -m ribeira_platform.migrations upgrade
```

Endpoints básicos:

```text
GET  /health/live
GET  /health/ready
POST /v1/tenants
POST /v1/tenants/{tenant_id}/properties
POST /v1/tenants/{tenant_id}/sources
POST /v1/tenants/{tenant_id}/properties/{property_id}/ingestions/{source_id}
POST /v1/tenants/{tenant_id}/properties/{property_id}/evaluate
```

## Testes

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## Limites deliberados

- O provider local de desenvolvimento não é autenticação de produção; produção
  exige JWT/OIDC, MFA/passkeys e revogação no Identity Provider.
- SQLite não executa consultas espaciais; o contrato PostGIS é a fonte para
  produção.
- Nenhum provedor externo é consultado sem endpoint/credencial configurado.
- A regra de 30% de umidade do blueprint é tratada como exemplo não aprovado;
  o motor só executa regras explicitamente registradas e ativas.

## Documentação

- `docs/requirements/REQUIREMENTS_TRACEABILITY.md`
- `docs/data/DATA_LINEAGE.md`
- `docs/provenance/PROVENANCE.md`
- `docs/security/THREAT_MODEL.md`
- `docs/architecture/ARCHITECTURE.md`
- `docs/adr/`
- `docs/operations/RUNBOOK.md`

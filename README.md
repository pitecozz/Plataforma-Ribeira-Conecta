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

O servidor usa SQLite local para desenvolvimento, sem exigir Docker ou PostgreSQL.
O schema alvo PostGIS está em `db/migrations/001_initial.sql`.

```bash
PYTHONPATH=src python3 -m ribeira_platform.api
```

Endpoints básicos:

```text
GET  /health
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

- O servidor local não autentica usuários; ele é uma superfície de
  desenvolvimento e a documentação marca o gateway/MFA/RBAC como gap de
  implantação.
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

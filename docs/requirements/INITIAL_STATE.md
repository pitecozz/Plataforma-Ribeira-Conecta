# Estado inicial e plano de execução

## Estado atual

No primeiro inventário, `/home/pitequin/RibeiraConectaIntelligencePlatform`
estava vazio, não era um checkout Git e não tinha JSON, backend, frontend,
schema, testes, CI/CD, observabilidade ou integrações. O blueprint primário foi
lido de `/home/pitequin/Downloads/ribeira_conecta_blueprint_completo.json` antes
de criar arquivos.

## Requisitos atendidos nesta execução

- núcleo multi-tenant com consultas escopadas por tenant;
- propriedade com GeoJSON/CRS e alvo PostGIS;
- adapter HTTP sem fallback fabricado;
- estados `SOURCE_UNAVAILABLE`, `UNKNOWN`, `INCONCLUSIVE` e `CONFLICTING`;
- evidência, proveniência, regra versionada, decisão, alerta, ação e auditoria;
- testes para dados ausentes, nulos, conflitos e tenant breakout;
- documentação de lineage, traceability, threat model e ADRs.

## Gaps

- autenticação/MFA/Passkeys/RBAC/ABAC;
- PostgreSQL/PostGIS executado e RLS verificado em ambiente real;
- providers oficiais reais, STAC, COG, object storage e workers geoespaciais;
- frontend GIS/Farm 360/Rule Studio;
- MQTT/LoRaWAN/device identity/edge;
- módulos Banana Intelligence, CRM, rastreabilidade e IA contextual;
- CI/CD com SAST, SCA, SBOM, DAST, image/IaC scanning;
- métricas, traces, filas, backup/DR e SIEM operacionais.

## Riscos

O servidor atual é uma superfície local de desenvolvimento. Não deve ser
publicado na internet: a API não possui autenticação nem TLS próprio. O adapter
HTTP ainda precisa de allowlist/egress proxy contra SSRF em produção. A regra de
30% de umidade é somente um exemplo do blueprint e não é criada automaticamente.

## Dados ausentes

- endpoints, licenças, credenciais e contratos de dados dos providers;
- polígonos reais, sensores reais e séries históricas;
- regra agronômica aprovada, limites por cliente/talhão e responsáveis;
- resultados de campo para validar modelos/diagnósticos;
- políticas comerciais confirmadas além das regras documentadas no prompt.

Não foram inventados valores para preencher esses campos.

## Decisões pendentes

- provider oficial e contrato de cada camada da fase 1;
- stack de frontend GIS e estratégia de tiles;
- política de identidade, papéis e segregação de funções;
- retenção LGPD, residência e classificação de dados;
- definição agronômica validada e processo de aprovação das regras;
- ambiente PostgreSQL/PostGIS, object storage, filas e observabilidade.

## Arquitetura proposta

Modular monolith com boundaries de source adapters, evidence engine, decision
engine, storage, API e workers futuros. PostgreSQL/PostGIS é o alvo produtivo;
SQLite é apenas o backend dependency-free de teste/local.

## Primeiro vertical slice

Entregue em `src/ribeira_platform`: propriedade -> fonte -> ingestão ->
observação/evidência -> regra -> conclusão -> alerta/ação -> audit log. O
workflow é executável por API e coberto por testes automatizados.

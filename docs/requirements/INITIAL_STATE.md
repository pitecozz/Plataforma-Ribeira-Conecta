# Estado inicial e plano de execução

## Estado atual

No primeiro inventário, `/home/pitequin/RibeiraConectaIntelligencePlatform`
estava vazio, não era um checkout Git e não tinha JSON, backend, frontend,
schema, testes, CI/CD, observabilidade ou integrações. O blueprint primário foi
lido de `/home/pitequin/Downloads/ribeira_conecta_blueprint_completo.json` antes
de criar arquivos.

## Requisitos atendidos na fundação e Fase 1A

- núcleo multi-tenant com consultas escopadas por tenant;
- propriedade com GeoJSON/CRS e alvo PostGIS;
- adapter HTTP sem fallback fabricado;
- estados `SOURCE_UNAVAILABLE`, `UNKNOWN`, `INCONCLUSIVE` e `CONFLICTING`;
- evidência, proveniência, regra versionada, decisão, alerta, ação e auditoria;
- testes para dados ausentes, nulos, conflitos e tenant breakout;
- documentação de lineage, traceability, threat model e ADRs;
- PostgreSQL/PostGIS real, migrations com checksum e rollback testado;
- RLS com `USING`, `WITH CHECK`, `FORCE RLS`, role não proprietária e testes reais;
- API FastAPI versionada com OpenAPI, JWT/OIDC boundary, RBAC default-deny,
  request/correlation IDs, health/readiness, limites e headers;
- SSRF policy/provider registry, idempotência, timestamps timezone-aware,
  métricas e gates CI de SAST/SCA/secret scan/SBOM.

## Gaps

- MFA/Passkeys via Identity Provider, ABAC completo, membership administrativo e
  revogação operacional;
- deployment gerenciado, TLS/WAF/rate limit distribuído, backup/DR/SIEM;
- providers oficiais reais, STAC, COG, object storage e workers geoespaciais;
- frontend GIS/Farm 360/Rule Studio;
- MQTT/LoRaWAN/device identity/edge;
- módulos Banana Intelligence, CRM, rastreabilidade e IA contextual;
- DAST, image/IaC scanning, pentest, canary e rollback de release;
- métricas, traces, filas, backup/DR e SIEM operacionais.

## Riscos

O compose e o provider de desenvolvimento são somente locais. A API não termina
TLS e ainda depende de edge/WAF/rate limit/egress proxy para exposição pública.
A regra de 30% de umidade é somente um exemplo do blueprint e não é criada
automaticamente.

## Dados ausentes

- endpoints, licenças, credenciais e contratos de dados dos providers;
- polígonos reais, sensores reais e séries históricas;
- regra agronômica aprovada, limites por cliente/talhão e responsáveis;
- resultados de campo para validar modelos/diagnósticos;
- políticas comerciais confirmadas além das regras documentadas no prompt;
- credenciais/licenças de providers externos e configuração de IdP.

Não foram inventados valores para preencher esses campos.

## Decisões pendentes

- provider oficial e contrato de cada camada da fase 1;
- stack de frontend GIS e estratégia de tiles;
- configuração do Identity Provider, papéis efetivos, MFA e segregação de funções;
- retenção LGPD, residência e classificação de dados;
- definição agronômica validada e processo de aprovação das regras;
- ambiente gerenciado PostgreSQL/PostGIS, object storage, filas e observabilidade.

## Arquitetura proposta

Modular monolith com boundaries de source adapters, evidence engine, decision
engine, storage, API e workers futuros. PostgreSQL/PostGIS é o caminho produtivo
validado nesta fase; SQLite é apenas o backend dependency-free de teste/local.

## Primeiro vertical slice

Entregue em `src/ribeira_platform`: propriedade -> fonte -> ingestão ->
observação/evidência -> regra -> conclusão -> alerta/ação -> audit log. O
workflow é executável por API e coberto por testes automatizados.

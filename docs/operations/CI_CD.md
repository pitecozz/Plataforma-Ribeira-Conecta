# CI/CD status

## Implementado no bootstrap

- compilação Python;
- testes unitários e de integridade;
- teste de isolamento multi-tenant;
- teste de ausência, conflito, `NULL` e fonte indisponível;
- workflow GitHub Actions básico.

## Gates ainda obrigatórios antes de produção

O workflow inicial não declara sucesso falso para controles ainda não instalados.
Devem ser adicionados antes do primeiro deploy público:

- format/lint/type check;
- SAST;
- SCA e secret scanning;
- SBOM e image scanning;
- IaC scanning;
- integration/contract/E2E/performance tests;
- DAST, pentest e revisão de threat model;
- test deploy, migration check, canary e rollback.

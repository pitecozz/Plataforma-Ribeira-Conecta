# CI/CD

O workflow `.github/workflows/ci.yml` executa gates reais:

- `ruff format --check`, `ruff check`, `mypy` e testes unitários;
- serviço PostgreSQL/PostGIS, migrations em banco limpo e testes de RLS/
  integração com role não proprietária;
- Bandit (SAST), pip-audit (SCA), detect-secrets e SBOM CycloneDX.

O arquivo `requirements.lock` fixa as versões observadas do ambiente de
desenvolvimento. A instalação usa o lock antes da instalação editável do
projeto; o pacote local é excluído do pip-audit por não ser uma distribuição
publicada.

Ainda não são gates desta fase: image scanning, IaC scanning, DAST, pentest,
test deploy, canary e rollback de release. Esses itens são risco residual e não
são simulados por um job que apenas imprime uma mensagem.

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

## Promoção controlada do frontend

Push de código não é implantação. A versão pública conhecida como boa continua
ativa até que uma candidata seja validada com a configuração protegida de
produção/OIDC, testes relevantes, build de produção e smoke isolado. Use
`ops/runtime/validate-production-frontend-candidate.sh` para gerar e testar
uma candidata fora de `frontend/dist`. Somente uma candidata aprovada pode ser
promovida com `ops/runtime/promote-frontend-candidate.sh`; esse procedimento
mantém o artefato anterior e o restaura se a validação posterior à promoção
falhar. Não execute esses scripts para cada commit de desenvolvimento.

O smoke não pode interpretar HTTP `200` como aplicação funcional: ele deve
validar o carregamento do JavaScript principal, a presença no bundle de cada
configuração pública obrigatória, a ausência das telas de bootstrap/configuração
e o worker MapLibre com MIME JavaScript. Transporte, processo, aplicação e
produto autenticado são estados distintos; a confirmação do produto requer E2E
ou aceitação manual adequada.

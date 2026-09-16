# Modelo de domínio comercial

## Bounded contexts

```text
Customer & Contract
  customer -> customer_contract -> contract_version -> subscription
  customer -> customer_property -> property

Catalog & Delivery
  product -> service -> service_plan
  installation_project -> installation -> asset -> asset_ownership

Commercial Finance
  capex_item / cost_item / revenue_item / pass_through_item
  pricing_policy -> pricing_policy_version
  operational_capacity_policy

Commercial Intelligence
  commercial_rule -> commercial_rule_version
  commercial_opportunity -> opportunity_evidence -> evidence
  prospect_scoring_model -> version -> factor
```

`BusinessApplication` é a porta de aplicação. `BusinessRepository` é um
adapter de persistência; os aggregates e engines não importam FastAPI,
PostgreSQL ou SQLite. O SQLite mantém apenas o caminho rápido de testes; o
PostgreSQL é o caminho de produção e aplica RLS.

## Identidade econômica

Ownership do ativo (`RIBEIRA_OWNED`, `CUSTOMER_OWNED`, `THIRD_PARTY`, `LEASED`,
`PASS_THROUGH`, `UNKNOWN`) é uma relação temporal com comprador, mantenedor,
responsável por substituição e portador de risco. A classificação de CAPEX é
armazenada separadamente e não é derivada somente de `asset_type`.

O tratamento de receita também é explícito. Um link externo pode existir no
contexto do cliente sem se tornar receita Ribeira. Um item pass-through pode
registrar valor, fornecedor, documento e data sem se tornar margem ou ativo.

## Evidência comercial

Uma oportunidade qualificada exige que a regra comercial avalie para `TRUE` e
que todos os `evidence_ids` existam no tenant. `UNKNOWN` gera conclusão
inconclusiva; `FALSE` não cria oportunidade. A oportunidade conserva rule ID,
versão, classificação e referências das evidências.

## Versionamento

Contratos, regras, preços, capacidade e modelos de score são registros
versionados com vigência. Uma nova versão não altera o conteúdo histórico usado
por uma decisão ou simulação anterior.

# Pricing Engine

O `PricingEngine` é um serviço de domínio independente da API HTTP. Ele aceita
uma `PricingPolicyVersion` vigente e um `CapitalBreakdown`:

```text
capital_liquido = capex_ribeira
                - margem_liquida_implantacao
                - outras_entradas_liquidas
```

O resultado contém status, valor monetário `Decimal`, moeda, inputs, fórmula,
policy ID/versão, classificação, premissas, dados ausentes, warnings e a marca
de simulação. `None` não vira zero. Entrada essencial ausente retorna
`INCOMPLETE_PRICING` sem valor final.

A política histórica de referência é carregada como dados versionados, não como
constante do controller. A validação impede descontinuidade para baixo na
transição de faixa e os testes percorrem a faixa de valores para preservar
monotonicidade. Simulações são marcadas como `SIMULATION` e não são persistidas
como fato comercial.

Valores negativos, infinitos e `NaN` são rejeitados. Arredondamento monetário
usa `Decimal` e `ROUND_HALF_UP` quando aplicável.

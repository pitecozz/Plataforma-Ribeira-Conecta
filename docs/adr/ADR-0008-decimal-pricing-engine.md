# ADR-0008 — Decimal e Pricing Engine separado

## Status

Aceito — Fase 1B.

## Contexto

Preços, CAPEX, margem e MRR exigem precisão monetária e explicação dos inputs.
Entradas ausentes não podem ser tratadas como zero.

## Decisão

Usar `Decimal` no domínio e em resultados financeiros, com moeda explícita,
validação de finitude/não negatividade e breakdown reproduzível. A fórmula é
armazenada em `pricing_policy_version` e executada por `PricingEngine`, fora da
camada HTTP. Simulações permanecem explicitamente marcadas.

## Consequências

O código de transporte precisa serializar Decimal de modo estável e o banco
usa `numeric`; testes de monotonicidade, fronteira, arredondamento e dados
ausentes tornam-se parte do contrato.

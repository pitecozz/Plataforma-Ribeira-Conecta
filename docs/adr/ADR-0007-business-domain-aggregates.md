# ADR-0007 — Aggregates comerciais e ownership explícito

## Status

Aceito — Fase 1B.

## Contexto

O domínio precisa representar serviços Ribeira, links de terceiros, ativos
instalados, pass-through e relações financeiras sem inferir ownership ou
receita a partir do tipo do equipamento.

## Decisão

Separar Customer/Contract, Catalog/Delivery, Commercial Finance e Commercial
Intelligence. Persistir ownership como relação temporal (`asset_ownership`),
tratamento de receita como enum explícito e oportunidade como aggregate que
referencia evidências do próprio tenant. Versões de contrato, regra, preço e
capacidade são registros novos, não mutações históricas.

## Consequências

O modelo tem mais relações e validações, mas permite auditar “quem comprou,
quem mantém e quem assume risco” e evita classificar automaticamente ISP,
pass-through ou projeto externo como receita Ribeira.

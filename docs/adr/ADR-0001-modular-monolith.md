# ADR-0001: Modular monolith + adapters

- Status: accepted
- Data: 2026-09-16

## Contexto

O workspace começou vazio, sem evidência de escala, ownership operacional ou
limites de deployment que justificassem microsserviços.

## Decisão

Usar modular monolith no domínio, com adapters de fontes e workers/eventos como
fronteiras futuras.

## Consequência

O primeiro slice é implantável e testável com menos superfície operacional. A
extração de serviços pode ocorrer sem mover regras para dentro de providers.

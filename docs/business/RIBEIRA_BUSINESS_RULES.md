# Regras de negócio da Ribeira Conecta — Fase 1B

Este documento separa regras confirmadas pelo Product Owner de premissas que
ainda não podem ser usadas como fatos. Valores financeiros, capacidade e
classificações são versionados no banco; este documento não substitui a versão
da política aplicada a uma decisão histórica.

## Regras confirmadas

| Regra | Classificação | Representação |
|---|---|---|
| A Ribeira Conecta não é automaticamente o provedor do link de internet. | `CONFIRMED` | contrato `EXTERNAL_LINK` com tratamento `CUSTOMER_DIRECT_EXTERNAL` ou `EXCLUDED` |
| O link pode ser contratado diretamente pelo cliente com um provedor externo. | `CONFIRMED` | contrato e receita com tratamento externo; não entra no MRR Ribeira |
| Projeto, instalação, distribuição interna, Wi-Fi, enlaces, gestão, monitoramento, manutenção e suporte podem ser serviços Ribeira. | `CONFIRMED` | catálogo configurável de produtos, serviços e planos |
| Ownership não é inferido pela localização física do ativo. | `CONFIRMED` | `asset_ownership` com vigência e responsabilidade explícitas |
| Hardware pass-through não é automaticamente CAPEX, margem ou MRR Ribeira. | `CONFIRMED` | `pass_through_item` e `RevenueTreatment.PASS_THROUGH` |
| Projeto técnico externo pago diretamente pelo cliente não é automaticamente receita Ribeira. | `CONFIRMED` | `InstallationProject` com `EXTERNAL_CONSULTANT` e tratamento externo |
| A referência operacional atual é até 10 instalações por mês. | `CONFIRMED` | política versionada `INSTALLATIONS_PER_MONTH`; não é constante de código |
| Acima da capacidade vigente deve existir `CAPACITY_GATE_REQUIRED`. | `CONFIRMED` | `CapacityEngine`; nenhuma expansão automática |
| O preço histórico de referência usa as faixas `MAX(500, capital * 15%)` até R$ 10.000 e `MAX(1500, capital * 12%)` acima disso. | `CONFIRMED` como política histórica | `PricingPolicyVersion`; não é verdade universal nem preço ativo sem publicação |
| Capital líquido usa CAPEX Ribeira menos margem líquida de implantação e outras entradas líquidas configuradas. | `CONFIRMED` | `CapitalBreakdown` transparente |
| MRR contém somente serviço recorrente elegível reconhecido pela Ribeira. | `CONFIRMED` | `Subscription.mrr_eligible` + `RIBEIRA_RECURRING` |
| Instalação, equipamento, pass-through, projeto externo e cobrança eventual não entram automaticamente no MRR. | `CONFIRMED` | filtros do cálculo de MRR |
| UNKNOWN não significa FALSE, ausência e nem zero. | `CONFIRMED` | engine comercial ternário e pricing incompleto |
| Oportunidade comercial exige evidência válida e não equivale a necessidade confirmada. | `CONFIRMED` | `CommercialOpportunity` + `opportunity_evidence` |

## Premissas

| Item | Classificação | Tratamento |
|---|---|---|
| `customer_type`, status de catálogo e tipos de contrato iniciais | `ASSUMPTION` | configuráveis; não são uma taxonomia comercial definitiva |
| Custos de imposto, deslocamento, terceiros, manutenção, risco e sinistro | `ASSUMPTION` | devem ser informados antes de um cálculo financeiro completo |
| Pesos e fatores de Prospect Score do blueprint | `ASSUMPTION` | apenas modelo configurável; nenhum peso é ativado sem versão publicada |
| SLA, churn, vida útil, payback e capacidade futura | `PENDING_VALIDATION` | não são calculados sem dados confirmados |
| Ativação comercial de produtos e serviços do catálogo | `PENDING_VALIDATION` | registros podem permanecer `DRAFT` ou `PILOT` |

## Política de ausência de dados

Entradas financeiras essenciais ausentes resultam em `INCOMPLETE_PRICING`;
capacidade sem política vigente resulta em `UNKNOWN`; regra comercial com fato
ausente resulta em `UNKNOWN`; oportunidade não é persistida sem evidência
existente no mesmo tenant. Nenhum desses estados é convertido em zero, false ou
fato comercial.

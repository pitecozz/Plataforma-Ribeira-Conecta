# Data quality e temporalidade

Estados suportados:

- `VALID`: payload aceito e observação elegível para regras;
- `UNKNOWN`: qualidade ou valor não determinável;
- `STALE`: dado existente, mas fora da janela de atualidade configurada;
- `INVALID`: valor não atende à validação semântica;
- `CONFLICTING`: fontes válidas divergem e não há precedência configurada;
- `SOURCE_UNAVAILABLE`: provider não respondeu;
- `INVALID_PAYLOAD`: provider respondeu com estrutura inválida.

Somente `VALID` com valor não nulo entra na regra atual. `NULL` não é convertido
em zero; `UNKNOWN` não é convertido em falso; dado indisponível não é substituído
por fallback não documentado. Conflitos ficam na decisão e em
`data_quality_event`.

Timestamps de observações e regras são exigidos timezone-aware e normalizados em
UTC para comparação. A representação original do timestamp é preservada em
`original_observation_timestamp` para auditoria do offset/provider.

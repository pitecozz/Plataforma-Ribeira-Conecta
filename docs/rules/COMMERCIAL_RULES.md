# Commercial Rule Engine

O engine comercial usa avaliação ternária:

```text
TRUE | FALSE | UNKNOWN
```

Um fato ausente permanece `UNKNOWN`. Para uma condição `all`, qualquer `FALSE`
domina; sem `FALSE`, um `UNKNOWN` torna o resultado `UNKNOWN`. Para `any`, um
`TRUE` domina; sem `TRUE`, um `UNKNOWN` mantém a conclusão inconclusiva.

Cada condição pode declarar `evidence_ids`. A aplicação só cria
`CommercialOpportunity` depois de verificar essas evidências no mesmo tenant.
O registro conserva `rule_id`, `rule_version`, classificação, status e a tabela
`opportunity_evidence`.

Regras ativas exigem criador e aprovador distintos. A autoridade é registrada
como `REGRA_COMERCIAL`, separada das autoridades agronômica, técnica,
regulatória, de cliente e de modelo. Vigência usa timestamps com timezone.

## Score de prospect

`ProspectScoringModelVersion` contém fatores, pontos e política para desconhecido:

```text
NEUTRAL | PENALIZE | BLOCK
```

O engine retorna score, fatores positivos/negativos, fatores desconhecidos e
evidências. Não há pesos ativos embutidos no código nem conversão de “não
observado” em “não existe”.

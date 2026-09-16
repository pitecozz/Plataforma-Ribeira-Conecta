# Contratos e versões

`customer_contract` representa a relação comercial; `contract_version`
representa o conteúdo válido em determinado intervalo. Versões são append-only
no fluxo de aplicação: alterações futuras criam uma nova versão e não
sobrescrevem a anterior.

Uma versão `ACTIVE` exige aprovador distinto do criador. A vigência é
timezone-aware e a busca de preço/regra/capacidade considera a janela
`valid_from <= instant < valid_until`.

O contrato registra o tratamento de receita. `EXTERNAL_LINK` só aceita
`CUSTOMER_DIRECT_EXTERNAL` ou `EXCLUDED`, evitando contabilização automática do
provedor externo como receita Ribeira. Subscriptions só contribuem para MRR
quando são recorrentes, elegíveis e têm tratamento `RIBEIRA_RECURRING`.

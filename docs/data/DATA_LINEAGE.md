# Data Lineage

```text
SOURCE
  -> RAW PROVIDER RESPONSE (preservada por raw_data_reference quando fornecida)
  -> INGESTION (status + timestamp + source version)
  -> NORMALIZATION (canonical Observation)
  -> VALIDATION (quality_flag; sem conversão de NULL para zero)
  -> EVIDENCE (observation -> source)
  -> RULE/MODEL (regra ativa + versão; modelo nulo neste slice)
  -> DECISION (classification/status/limitations/missing/conflicts)
  -> ALERT/ACTION
  -> AUDIT LOG
```

## Contratos de integridade

- `NULL` continua `NULL`; não é convertido em zero.
- `UNKNOWN` não é convertido em `false`.
- Uma fonte sem endpoint produz `SOURCE_UNAVAILABLE`, não um valor default.
- Observação externa chega como `OBSERVED`; resultado de regra é `CALCULATED` ou
  `INFERRED` conforme o significado.
- O resultado agronômico atual é uma suspeita operacional, nunca diagnóstico.
- Timestamp de observação e timestamp de ingestão são campos distintos.
- `tenant_id` percorre todas as entidades e consultas locais.
- O schema de produção preserva `crs`, unidade, resolução, versão e checksum.

## Snapshot e reprodutibilidade

Uma decisão guarda IDs de evidência, regra/versão, modelo/versão (nulos quando
não utilizados), limitações, dados ausentes e conflitos. Isso permite reconstruir
o motivo da decisão sem reclassificar uma hipótese como observação atual.

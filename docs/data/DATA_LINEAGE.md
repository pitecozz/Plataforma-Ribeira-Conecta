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

## Geospatial Phase 1C

```text
Property.geometry + geometry_crs
  -> explicit WGS84 transformation
  -> CDSE STAC search request
  -> raw paginated STAC response
  -> SatelliteScene + SatelliteAsset catalogue
  -> scene selection policy/version
  -> SATELLITE_SCENE evidence
  -> ProcessingJob
  -> RED/NIR assets + AOI crop
  -> NDVI formula/version
  -> COG + statistics + checksum
  -> DERIVED_PRODUCT evidence
```

Acquisition, provider publication, ingestion and processing timestamps remain
separate. Nodata is not zero. `s3://` asset references are catalogued but not
claimed as downloaded unless a controlled asset adapter succeeds.

For authenticated CDSE processing, the asset segment is explicit:

```text
CDSE STAC Item
  -> s3://eodata object reference
  -> exact bucket/key validation
  -> authenticated CDSE S3 access
  -> bounded local file + SHA-256
  -> RED/NIR AOI windows
  -> NDVI algorithm/version
  -> validated COG + statistics
```

Missing credentials, rejected credentials, disallowed buckets, oversized
objects and unavailable objects are quality outcomes. They never become zero,
empty rasters or fabricated statistics.

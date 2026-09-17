# Provenance and Evidence Model

## Entidades

- `source`: fornecedor, tipo, endpoint, versão e estado.
- `observation`: valor canônico com timestamp, unidade, CRS, resolução, quality
  flag, checksum e referência bruta.
- `evidence`: liga uma observação a sua fonte e registra transformação e
  limitações.
- `decision`: liga a conclusão às evidências, regra/modelo e dados ausentes.
- `audit_log`: registra actor, entrada, versão e resultado.

## Evidence Chain

```text
conclusion
  -> decision.evidence_ids
  -> evidence.reference_id
  -> observation.source_id
  -> source.provider / source_version / endpoint
```

Nenhum valor de confiança é gerado pelo slice. `confidence = null` porque não há
metodologia validada para um score de confiança neste momento.

## Geospatial Evidence Chain

```text
CDSE STAC response reference
  -> SatelliteScene.external_item_id + checksum
  -> SatelliteAsset.href/title/roles
  -> scene-selection policy/version
  -> ProcessingJob algorithm/version/parameters
  -> DerivedProduct output checksum/statistics
  -> DERIVED_PRODUCT evidence
```

Scene metadata is classified as `OFFICIAL_SOURCE`. NDVI is `DERIVED`, carries
its formula and input asset keys, and does not assert disease, cause or current
field condition. When provider assets are unavailable, the job records
`ASSET_UNAVAILABLE` and no statistic is emitted.

With authenticated assets, the chain also records the configured CDSE endpoint
and bucket, object keys, access status, acquired byte count, local checksum,
provider checksum when explicitly returned, local object reference, AOI
checksum, algorithm/version and processing timestamps. Secret keys and
authorization headers are never provenance or audit data.

`tests/integration/test_geospatial_postgres.py` exercises this persistence chain
against PostgreSQL/PostGIS and RLS using data explicitly marked
`synthetic_test_data`. It proves storage relationships and tenant isolation; it
does not represent a live CDSE observation. Live asset verification remains
opt-in through `RIBEIRA_CDSE_S3_EXTERNAL_TEST=1`.

## Conflitos

Valores diferentes do mesmo métrico e timestamp, provenientes de fontes
distintas, geram `CONFLICTING`; o motor não escolhe o mais conveniente. A decisão
fica inconclusiva e cria alerta/ação de resolução sem responsável inventado.

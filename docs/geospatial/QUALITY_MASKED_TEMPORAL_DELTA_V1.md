# Quality-masked temporal delta V1

Phase 1F processes persisted Sentinel-2 L2A assets once, then serves the
result through the existing authorized COG tile flow. The browser does not
download RED, NIR or SCL, and it never recomputes an NDVI mask or delta.

## Sentinel-2 SCL policy

`SENTINEL2_SCL_CONSERVATIVE_V1` uses the official Sentinel-2 L2A `SCL_20m`
asset resampled with nearest neighbour onto the RED 10 m AOI grid.

| SCL class | V1 policy |
| --- | --- |
| 0 no data; 1 saturated/defective; 2 topographic shadow; 3 cloud shadow | excluded |
| 4 vegetation; 5 bare soil; 6 water | accepted |
| 7 unclassified | optional/policy-dependent; excluded conservatively in V1 |
| 8/9 cloud probability; 10 cirrus; 11 snow/ice | excluded |

Bare soil and water remain accepted: their NDVI is mathematically meaningful.
SCL class, local checksum, accepted/excluded class sets, policy version and
discarded pixels are persisted in the quality-masked product parameters.
Temporal-delta creation and read paths fail closed unless both upstream products
retain that complete, internally consistent mask record. Property-scoped jobs
remain backward compatible. An optional field/talhão-scoped job snapshots the
exact tenant-local `field_id`, property, immutable boundary version and SHA-256
geometry checksum on both job and product; PostgreSQL composite foreign keys and
the equivalent test-store lookup reject tenant/property/version/checksum drift.
Processing transforms that exact snapshot geometry to the baseline grid and
clips both already quality-masked NDVI inputs before subtraction. Comparison
lookup includes the optional field identity, so a property-wide delta cannot be
replaced by a field-clipped result for the same upstream pair, and one field's
delta cannot be returned for another field. Only pixels inside the field and
finite in both inputs contribute; valid, nodata and coverage statistics still
describe the full output grid, and both upstream dependencies remain explicit. Legacy, mismatched or tampered field provenance is not eligible
for `FIELD` rules. The authenticated temporal-delta evaluation uses only the
persisted mean as `ndvi_temporal_delta_mean`, preserves the derived-product
evidence, field boundary snapshot and exact selected rule version/scope, and creates
an alert plus a non-automated targeted field-inspection recommendation only when
the rule triggers. Invalid provenance or no applicable rule is `INCONCLUSIVE`; field rules have
precedence only for a valid field-clipped delta, followed by property, customer
and tenant scope. A valid non-trigger is `NO_TRIGGER`. Farm360 exposes this evaluation only to
users with both `geospatial:read` and `decision:evaluate`, then refreshes the
persisted decision/action workflow. The delta never constitutes a diagnosis.
Scene `eo:cloud_cover` remains scene metadata; it is not AOI valid coverage.

## Scientific processing

For a quality-masked product, a valid pixel is inside the AOI and has valid RED,
valid NIR, a non-zero finite denominator, and an accepted SCL class. Invalid
pixels are NaN nodata, never NDVI zero. The scientific COG remains float.

The delta product chooses the baseline quality-masked NDVI grid deterministically.
If CRS, transform, dimensions and resolution match, it reads both directly. If
they differ, target is reprojected explicitly to that baseline grid using
bilinear resampling and the operation is recorded as
`ALIGNED_TO_BASELINE_GRID`. A delta pixel exists only
where both masked NDVIs are finite:

```text
delta = target_ndvi - baseline_ndvi
```

`comparable_coverage_percentage` uses all baseline-grid reference pixels as its
denominator. A positive value only means target NDVI is numerically higher; it
does not identify disease, water status, fertility, yield, gain or loss.

## Evidence chain

```text
NDVI delta COG -> delta ProcessingJob -> baseline/target dependencies
  -> quality-masked NDVI -> RED + NIR + SCL -> Sentinel scene -> CDSE STAC
```

`derived_product_dependency` records `BASELINE_NDVI` and `TARGET_NDVI` under
tenant RLS. A delta COG has an independent checksum and never overwrites either
NDVI. The existing derived-product tile endpoint applies the same authorization,
private cache and `Vary: Authorization` controls; it renders a diverging palette
only for display, without modifying raster values.

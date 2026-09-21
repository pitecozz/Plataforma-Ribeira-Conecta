# Soil Intelligence

Soil Intelligence is a Farm360/Agro capability that turns evidence about a
verified property, field/talhão, management zone or asset into reviewable
agronomic context. It follows the shared chain:

`asset -> data -> context -> rule -> decision -> action -> result`

It combines remote sensing, terrain, weather, hydrology, historical records,
field measurements and laboratory evidence only when their provenance,
timestamp, spatial scope and limitations are retained. A satellite estimate is
not a laboratory or in-situ measurement.

## Evidence classes

| Evidence | Permitted classification | Limitation |
|---|---|---|
| SoilGrids, PronaSolos/Embrapa or future official soil maps | `MODELLED`/`DERIVED` or `OFFICIAL_SOURCE`, as returned | Baseline/context, not a field sample. |
| Sentinel-1/2, Landsat 8/9, SMAP | `DERIVED`/`MODELLED` | May indicate surface moisture, waterlogging, vegetation and variability; never direct field chemistry. |
| Copernicus DEM and derived slope/drainage | `OFFICIAL_SOURCE` + `CALCULATED`/`DERIVED` | Terrain representation and resolution remain explicit. |
| INMET/WIS2, approved weather providers or local station | `OBSERVED`/`OFFICIAL_SOURCE` | Station representativeness and gaps remain explicit. |
| Calibrated field sensor | `OBSERVED` | Device, installation depth, calibration and quality are required. |
| Georeferenced lab result | `LAB_MEASURED` in the future domain mapping; currently preserve the source-specific measured classification and raw evidence | Applies only to sample/time/depth. |

Remote sensing must never be presented as a direct pH, P, K, Ca, Mg,
micronutrient or chemical-fertility measurement. Model predictions and virtual
measurements are always `DERIVED` or `PREDICTED`, never `OBSERVED`.

## Source and provider policy

Soil and remote datasets use the provider-neutral interfaces documented in
`docs/geospatial/PROVIDER_ABSTRACTION.md`: Copernicus CDSE, optional GEE,
USGS/NASA, JRC and future official providers remain replaceable. Google Earth
visualization imagery is not a source contract. Source, collection/dataset,
request, transformation/model, version, coverage, license/terms and limitations
are persisted per result.

## Planned entities and safety gates

Existing Digital Twin entities remain canonical: property, field/talhão,
sensor, weather station, irrigation equipment, sample location and access
infrastructure are spatial assets/context where possible. Module-specific
duplicates are prohibited.

- `AGRICULTURAL_MANAGEMENT_ZONE`: derived spatial similarity zone, versioned
  geometry, method, input evidence, generated time and limitations; never a
  cadastral boundary.
- `SOIL_SAMPLE`: confirmed collection location, depth, time, collector, sample
  ID and laboratory chain of custody.
- `LABORATORY_SOIL_RESULT`: normalized core analytes (such as pH, P, K, Ca, Mg,
  organic matter, CEC, texture and micronutrients) plus provider-specific raw
  attributes/evidence. No universal schema is assumed.
- `VIRTUAL_SOIL_SENSOR`: a later estimate with uncertainty, input provenance,
  model/version and calibration timestamp.

Disease and crop-management policies require approved agronomic source or
qualified expert review: `EXPERT_VALIDATION_REQUIRED`. Missing soil chemistry,
calibration, field inspection or provider data remains `UNKNOWN`/
`INCONCLUSIVE`.

## Commercially useful, evidence-backed outputs

Future outputs include preliminary land suitability, Banana Suitability,
management zones, smart sampling plans, sensor deployment design, lab-data
integration, waterlogging/flood risk context and recurring Farm360 reports.
They become commercial opportunities only through evidence -> applicable need
-> service; absence of data is never a fabricated sales recommendation.

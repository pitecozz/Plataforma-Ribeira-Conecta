# Agricultural Land Suitability

`AGRICULTURAL_LAND_SUITABILITY` is a reviewable suitability workflow for a
verified property and optional verified field/talhão. A user may draw an
`ANALYSIS_AREA`, select a crop and request analysis. The drawn polygon is not a
legal property, survey, CAR, land-title or official georeferencing boundary.

## Result contract

Each analyzed zone records geometry, area, source inputs, method/version,
generation time, supporting evidence, constraints, missing data, uncertainty
and recommended next action. It returns an explainable state:

`HIGH`, `MODERATE`, `LOW`, `UNSUITABLE`, `INCONCLUSIVE` or `UNKNOWN`.

Preliminary results use a clearly labelled `PRELIMINARY_*` form. They may use
terrain, climate, soil baselines, hydrology, satellite and historical context.
`VALIDATED_SUITABILITY` additionally requires suitable laboratory results,
verified field observations, agronomic inspection and/or calibrated sensors as
relevant to the claim. Promotion is explicit and auditable; it is never
automatic.

## Banana Suitability Intelligence

`BANANA_SUITABILITY_INTELLIGENCE` is the crop-specific implementation. Possible
inputs include elevation, slope, drainage, rainfall/temperature/humidity,
water availability, soil context, vegetation and land-cover history, observed
flood/waterlogging exposure, watercourse proximity, access/infrastructure,
inspections and measured samples. Factors are used only when supported by an
approved agronomic rule/source. No universal banana threshold is hardcoded.

The shared flood event/exposure domain is reused for waterlogging/flood context;
Agro does not create a competing flood model. Satellite flood/open-water
signals remain derived evidence, not crop loss or flooded-hectare claims.

## Can I plant here?

1. Select verified property and optional field; draw `ANALYSIS_AREA`.
2. Select crop and request assessment.
3. Return analyzed area, preliminary/validated status, positives, constraints,
   unknowns, uncertainty and validation actions.

For example, `PRELIMINARY_MODERATE` may say terrain is acceptable, waterlogging
is a constraint and recent soil chemistry is unknown, then recommend smart soil
sampling. It must not imply legal demarcation or agronomic certainty.

Farm360's planned Soil/Land Suitability view exposes property/analysis areas,
fields, zones, baseline, sensors, samples, slope/drainage, waterlogging,
satellite indicators and suitability layers with source, date, classification
and uncertainty on every layer.

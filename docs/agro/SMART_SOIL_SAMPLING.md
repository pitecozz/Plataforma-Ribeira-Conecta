# Smart Soil Sampling and Management Zones

`SMART_SOIL_SAMPLING` uses available terrain, soil baseline, Sentinel/Landsat
variability, moisture/waterlogging context, vegetation history, hydrology and
prior confirmed samples to propose cost-effective sampling zones. It does not
create a soil measurement.

`AGRICULTURAL_MANAGEMENT_ZONES` are versioned derived geometry with derivation
method, inputs, generated time and limitations. They are neither property nor
cadastral boundaries. A suggested sample location is
`RECOMMENDED_ACTION`/`DERIVED_LOCATION` until a technician confirms collection.

Workflow:

`suggest zone -> technician confirms/adjusts -> collection -> sample ID ->`
`geolocation/depth/time -> laboratory -> import -> validation -> Soil`
`Intelligence update -> suitability recalculation`

Traceability links the derived suggestion, confirmation, sample, lab/provider
raw evidence, normalized result, validation, recomputation and resulting
decision/action/outcome. Sampling density and sensor deployment are selected
by information value and risk; whole-farm point-sensor coverage is not assumed.

Future `MOBILE_SOIL_EC_SURVEY` may support zone delineation and sampling
optimization. EC is an indirect spatial variability indicator, never a direct
fertilizer requirement.

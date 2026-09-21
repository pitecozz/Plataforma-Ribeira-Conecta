# Field Telemetry and Smart Field Sensing

Planned field-sensor assets include soil moisture, matric potential, soil
temperature and electrical conductivity; optional later sensors include leaf
wetness, sap flow and canopy temperature. A local weather station may measure
rainfall, air temperature, relative humidity, pressure, wind and solar
radiation. Deployment is need/risk/evidence driven, not a mandatory bundle.

Every reading will preserve sensor asset ID, property/field, coordinates,
installation depth, measurement type/unit, observed/received time, quality,
calibration, manufacturer/model, battery, communication health and source
provenance. Observed sensor values never mix with modelled estimates.

Supported adapter patterns are LoRaWAN, NB-IoT, LTE-M, 4G/LTE, appropriate
Wi-Fi and future provider adapters:

`sensor -> network/gateway -> MQTT or HTTPS -> telemetry ingress -> Digital`
`Twin -> Rules -> Decision -> Action -> Outcome`

MQTT, HTTPS/webhook and batch/API imports require tenant-bound device identity,
authenticated ingress, schema/unit/time validation, deduplication, quality
state, source health and audit provenance. There is no unauthenticated public
device ingress and no vendor lock-in.

`VIRTUAL_SOIL_SENSOR`, `FIELD_WATER_BALANCE` and
`IRRIGATION_DECISION_SUPPORT` are later capabilities. They may combine sparse
physical sensors, rainfall, evapotranspiration, terrain, soil context and
remote data, but output `DERIVED`/`PREDICTED` estimates with uncertainty,
model/version and calibration. Automated irrigation or actuation requires a
separate validated agronomic and safety/control design. `CRNS_SOIL_MOISTURE` is
specialized/research (`LATER`), not MVP. `DRONE_SURVEY` is optional and records
flight/payload/capture/spatial-accuracy provenance; it complements rather than
replaces satellite or field evidence. `PLANT_RESPONSE_INTELLIGENCE` is research
context and never a remote-imagery-only disease diagnosis.

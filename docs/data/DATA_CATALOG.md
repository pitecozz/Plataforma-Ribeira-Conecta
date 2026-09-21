# Data catalogue and dictionary

This index complements [data lineage](DATA_LINEAGE.md) and does not replace
database migrations as the physical schema authority. Each record preserves
tenant/owner scope where applicable, classification, timestamps, source and
units; retention policy is `TO_DEFINE` per legal/operational category.

| Entity | Meaning / key relationships | Classification, unit and scope |
|---|---|---|
| Tenant / customer / prospect | Isolation and commercial subject; customer/prospect may link to properties. | Tenant-owned; minimal personal data and authorization apply. |
| Property / field/talhão / analysis area | Physical context; field and analysis area relate to property. | Geometry/CRS/source; analysis area is not a legal boundary. |
| Management zone | Versioned derived spatial similarity area. | Method, inputs, generated time and limitations required. |
| Asset / sensor | Digital Twin entity or device tied to property/context. | Ownership, geometry, status and device calibration are explicit. |
| Observation / telemetry | Timestamped measured/provider record. | `OBSERVED` is distinct from modelled value; unit, observed/received times and quality required. |
| Sample / laboratory result | Field collection and lab chain-of-custody result. | Location/depth/time/lab/raw evidence; a sample is not a zone-wide truth. |
| Event / exposure | Factual event profile/hypotheses and tenant-isolated spatial assessment. | Facts, hypotheses and calculated exposure remain separated. |
| Source / provider / evidence | Origin and link used by decisioning. | Provider, dataset, request, transformation, licence/terms and limitations. |
| Scene / raster product | Catalogue item and derived spatial product. | Acquisition/processing times, CRS/resolution, algorithm/checksum; coverage is explicit. |
| Rule / decision / action / outcome | Operational decision chain and closure. | Version, applicability, evidence, actor, limitations and audit are required. |
| Report | Traceable presentation of selected context and conclusions. | Report version, generation time, sources, classifications and limitations. |

Classification vocabulary includes `OBSERVED`, `OFFICIAL_SOURCE`,
`MANUAL_CONFIRMED`, `CALCULATED`, `DERIVED`, `INFERRED`, `PREDICTED`,
`ASSUMPTION`, `SIMULATED`, `UNKNOWN` and `CONFLICTING`. A future lab-specific
mapping must retain the provider's measured meaning and never relabel remote
context as a lab result.

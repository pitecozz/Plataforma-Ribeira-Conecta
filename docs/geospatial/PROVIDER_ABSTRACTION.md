# Replaceable remote-sensing and data-provider architecture

Remote-sensing providers are independent data-access/processing providers behind
common domain interfaces. A satellite mission, a catalogue, a processing
service, and visualization imagery are different concepts and must not be
silently substituted for one another.

```text
Domain request / explicit selection policy
  -> provider-neutral catalogue, asset-access, and processing ports
  -> provider-specific adapter
  -> source response + dataset/collection/item/asset provenance
  -> tenant-scoped evidence, decision, action and result
```

## Provider roles

| Provider | Potential role | Constraint |
|---|---|---|
| Copernicus CDSE | Official Sentinel catalogue and controlled asset access | Current adapter; provider-specific endpoint and credential gate remain enforced. |
| Google Earth Engine | Optional processing and data-access provider | Future opt-in adapter only; not required for current processing. |
| USGS/NASA | Independent Landsat and complementary official dataset access | Future provider contracts/adapters; no assumed endpoint or product availability. |
| JRC | Independent reference datasets, such as water-context products | Future dataset-specific adapter and versioned methodology. |
| Future providers | Redundant catalogue, asset or processing paths | Must implement the same bounded contracts and provenance gates. |

Google Earth is **not** a satellite-source contract. Google Earth visualization
imagery is never evidence, a processing input, or a fallback for a missing
provider dataset.

## Mission and provider independence

Sentinel-1, Sentinel-2, Landsat 8 and Landsat 9 are mission/dataset identities,
not hard dependencies on one provider. The platform may obtain them through
independent/provider-neutral adapters where their official contract, licence,
temporal/spatial characteristics and processing semantics are known. Provider
redundancy means an alternate provider can be selected explicitly; it never
means silently mixing items, switching a source after a failure, or treating
products from unlike pipelines as comparable.

## Common-port minimum contract

Every provider adapter must declare and validate:

- provider identity, endpoint, authority, licence/terms, authentication state,
  request bounds and dataset/collection capability;
- mission, platform, collection/product identifiers, acquisition time, geometry
  and CRS, resolution, processing level/version, available bands/polarization,
  assets/checksums and source response reference;
- request parameters, selection policy/version, transformations, processing
  algorithm/version, generated time, raw-reference retention and limitations;
- whether an item is `OBSERVED`, `OFFICIAL_SOURCE`, `DERIVED`, `CALCULATED`,
  `INFERRED`, `UNKNOWN` or another explicit project classification.

The adapter returns explicit `SOURCE_UNAVAILABLE`, credential, licence,
coverage, quality and compatibility outcomes. It must not replace missing data,
invent coverage, convert provider failure into another provider's output, or
promote a visual layer to evidence.

## Integration path

1. Register each provider and its capabilities centrally; retain its official
   documentation/terms and allowlisted endpoints.
2. Add a bounded adapter and contract fixtures without modifying domain rules.
3. Add an opt-in external smoke test using a non-customer AOI; credentials stay
   in runtime secret storage.
4. Persist provider/dataset/item/asset provenance and compatibility before any
   processing request.
5. Permit provider selection or redundancy only through an explicit policy and
   record the decision, limitations and comparability analysis.

Earth Engine, Landsat and JRC remain roadmap work until those gates are met.

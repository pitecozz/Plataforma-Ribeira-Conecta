# Copernicus Data Space Ecosystem provider

The Phase 1C adapter uses the current official CDSE STAC catalogue:

- Documentation: <https://documentation.dataspace.copernicus.eu/APIs/STAC.html>
- Catalogue: `https://stac.dataspace.copernicus.eu/v1/`
- Provider: `COPERNICUS_CDSE`
- API standard: STAC
- Catalogue version observed: STAC 1.1.0
- Initial collection: `sentinel-2-l2a`
- Metadata captured: 2026-09-16

The endpoint and provider metadata are registered centrally. Controllers do not
contain CDSE URLs. The collection response reported title `Sentinel-2
Level-2A` and license value `other`; the adapter deliberately does not infer a
stronger license or authentication policy. The live catalogue returned real
items with `s3://eodata/...` assets. Metadata discovery therefore works without
claiming that protected raster assets were downloaded.

The official CDSE documentation states that the former catalogue endpoint is
deprecated, so the legacy endpoint is not used. Asset access is a separate,
controlled policy and is not opened with a wildcard allowlist.

## Authenticated asset access

The official S3 documentation identifies the default S3-compatible endpoint as
`https://eodata.dataspace.copernicus.eu/`, with bucket `eodata`. Credentials are
created through the CDSE account/S3 credentials manager and are supplied only by
the runtime environment. The repository contains names, never credential
values:

```text
CDSE_S3_ACCESS_KEY
CDSE_S3_SECRET_KEY
CDSE_S3_ENDPOINT
CDSE_S3_BUCKET
```

`CdseS3AssetAdapter` parses only `s3://eodata/<object-key>`, uses the configured
HTTPS endpoint rather than the URI authority, requires path-style SigV4 access,
and streams only bounded RED/NIR assets into tenant-scoped local object storage.
It records local SHA-256 and provider checksum metadata when the provider
supplies it. Missing credentials produce `BLOCKED_BY_CREDENTIAL`; rejected
credentials produce `PROVIDER_AUTHENTICATION_FAILED`. Neither state emits NDVI.

Official references used:

- <https://documentation.dataspace.copernicus.eu/APIs/S3.html>
- <https://documentation.dataspace.copernicus.eu/notebook-samples/geo/stac_ndvi.html>

## External verification

Run the controlled network test explicitly:

```bash
RIBEIRA_CDSE_EXTERNAL_TEST=1 PYTHONPATH=src \
  .venv/bin/python -m unittest tests.integration.test_cdse_external -v

The authenticated asset test additionally requires
`RIBEIRA_CDSE_S3_EXTERNAL_TEST=1` plus runtime credentials. Without them it is
skipped with an explicit reason; the normal suite remains offline-safe.
```

Its AOI is `TEST_AOI_ONLY` and cannot create a customer record or commercial
opportunity.

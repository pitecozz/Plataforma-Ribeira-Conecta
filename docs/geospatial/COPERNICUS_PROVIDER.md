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

## Credentials and asset limitation

The official notebook documents CDSE S3 credentials for CloudFerro data assets.
No credentials are committed or assumed. If they are absent, the processing job
ends with `ASSET_UNAVAILABLE`; no NDVI value is fabricated.

## External verification

Run the controlled network test explicitly:

```bash
RIBEIRA_CDSE_EXTERNAL_TEST=1 PYTHONPATH=src \
  .venv/bin/python -m unittest tests.integration.test_cdse_external -v
```

Its AOI is `TEST_AOI_ONLY` and cannot create a customer record or commercial
opportunity.

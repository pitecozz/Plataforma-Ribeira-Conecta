-- Phase 1C.1: bounded authenticated access to CDSE S3 assets.
-- Secrets are deliberately not stored here.

ALTER TABLE provider_registry ADD COLUMN IF NOT EXISTS asset_endpoint text;
ALTER TABLE provider_registry ADD COLUMN IF NOT EXISTS asset_bucket text;

UPDATE provider_registry
SET asset_endpoint = 'https://eodata.dataspace.copernicus.eu',
    asset_bucket = 'eodata'
WHERE provider_id = 'COPERNICUS_CDSE';

ALTER TABLE satellite_asset ADD COLUMN IF NOT EXISTS checksum_provider text;
ALTER TABLE satellite_asset ADD COLUMN IF NOT EXISTS checksum_local text;
ALTER TABLE satellite_asset ADD COLUMN IF NOT EXISTS checksum_algorithm text;
ALTER TABLE satellite_asset ADD COLUMN IF NOT EXISTS download_status text;
ALTER TABLE satellite_asset ADD COLUMN IF NOT EXISTS download_started_at timestamptz;
ALTER TABLE satellite_asset ADD COLUMN IF NOT EXISTS download_finished_at timestamptz;
ALTER TABLE satellite_asset ADD COLUMN IF NOT EXISTS local_reference text;
ALTER TABLE satellite_asset ADD COLUMN IF NOT EXISTS bytes_downloaded bigint;

ALTER TABLE satellite_asset
  ADD CONSTRAINT satellite_asset_bytes_downloaded_check
  CHECK (bytes_downloaded IS NULL OR bytes_downloaded >= 0);

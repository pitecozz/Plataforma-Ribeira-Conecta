-- Shared Digital Twin context for existing tenant assets; no inferred facts.
ALTER TABLE asset
  ADD COLUMN geometry geometry(Geometry,4326),
  ADD COLUMN geometry_crs text,
  ADD COLUMN source_reference text,
  ADD COLUMN observed_at timestamptz,
  ADD COLUMN context jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE asset ADD CONSTRAINT asset_geometry_crs_check
  CHECK (geometry IS NULL OR geometry_crs IN ('EPSG:4326','CRS:84'));
CREATE INDEX asset_geometry_gix ON asset USING gist(geometry);

-- Phase 1C: tenant-scoped STAC discovery and controlled raster processing.
-- Provider and collection metadata are global configuration; scenes and
-- derivatives are tenant-scoped copies for isolation and auditability.

ALTER TABLE provider_registry ADD COLUMN IF NOT EXISTS organization text;
ALTER TABLE provider_registry ADD COLUMN IF NOT EXISTS provider_type text;
ALTER TABLE provider_registry ADD COLUMN IF NOT EXISTS documentation_url text;
ALTER TABLE provider_registry ADD COLUMN IF NOT EXISTS catalog_endpoint text;
ALTER TABLE provider_registry ADD COLUMN IF NOT EXISTS api_standard text;
ALTER TABLE provider_registry ADD COLUMN IF NOT EXISTS stac_version text;

INSERT INTO provider_registry (
  provider_id, name, category, authority, endpoint, license,
  authentication_type, version, status, organization, provider_type,
  documentation_url, catalog_endpoint, api_standard, stac_version
)
VALUES (
  'COPERNICUS_CDSE',
  'Copernicus Data Space Ecosystem',
  'EARTH_OBSERVATION',
  'COPERNICUS',
  'https://stac.dataspace.copernicus.eu/v1/',
  'other',
  'NOT_DETERMINED',
  'STAC 1.1.0',
  'ACTIVE',
  'Copernicus Data Space Ecosystem',
  'EARTH_OBSERVATION',
  'https://documentation.dataspace.copernicus.eu/APIs/STAC.html',
  'https://stac.dataspace.copernicus.eu/v1/',
  'STAC',
  '1.1.0'
)
ON CONFLICT (provider_id) DO UPDATE SET
  name = EXCLUDED.name,
  endpoint = EXCLUDED.endpoint,
  documentation_url = EXCLUDED.documentation_url,
  catalog_endpoint = EXCLUDED.catalog_endpoint,
  api_standard = EXCLUDED.api_standard,
  stac_version = EXCLUDED.stac_version,
  status = EXCLUDED.status;

CREATE TABLE IF NOT EXISTS geospatial_collection (
  provider_id text NOT NULL REFERENCES provider_registry(provider_id),
  external_collection_id text NOT NULL,
  title text,
  mission text,
  processing_level text,
  spatial_resolution text,
  temporal_characteristics jsonb NOT NULL DEFAULT '{}'::jsonb,
  bands jsonb NOT NULL DEFAULT '{}'::jsonb,
  license text,
  stac_version text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  retrieved_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (provider_id, external_collection_id)
);

CREATE TABLE IF NOT EXISTS satellite_search (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  property_id uuid NOT NULL,
  provider_id text NOT NULL REFERENCES provider_registry(provider_id),
  collection_id text NOT NULL,
  datetime_start timestamptz NOT NULL,
  datetime_end timestamptz NOT NULL,
  aoi geometry(Geometry, 4326) NOT NULL,
  source_crs text NOT NULL,
  target_crs text NOT NULL,
  transformation text NOT NULL,
  policy_id text NOT NULL,
  policy_version integer NOT NULL,
  cloud_cover_limit numeric(6,3),
  status text NOT NULL,
  candidate_count integer NOT NULL DEFAULT 0,
  selected_scene_id uuid,
  raw_metadata_reference text,
  quality jsonb NOT NULL DEFAULT '[]'::jsonb,
  failure_reason text,
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, property_id) REFERENCES property(tenant_id, id),
  FOREIGN KEY (provider_id, collection_id)
    REFERENCES geospatial_collection(provider_id, external_collection_id),
  CHECK (datetime_end > datetime_start),
  CHECK (cloud_cover_limit IS NULL OR cloud_cover_limit BETWEEN 0 AND 100)
);
CREATE INDEX IF NOT EXISTS satellite_search_property_idx
  ON satellite_search (tenant_id, property_id, created_at DESC);
CREATE INDEX IF NOT EXISTS satellite_search_aoi_gix
  ON satellite_search USING gist (aoi);

CREATE TABLE IF NOT EXISTS satellite_scene (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  property_id uuid NOT NULL,
  provider_id text NOT NULL REFERENCES provider_registry(provider_id),
  collection_id text NOT NULL,
  external_item_id text NOT NULL,
  acquisition_datetime timestamptz NOT NULL,
  provider_published_datetime timestamptz,
  geometry geometry(Geometry, 4326) NOT NULL,
  bbox jsonb NOT NULL,
  cloud_cover numeric(6,3),
  platform text,
  constellation text,
  processing_level text,
  stac_version text NOT NULL,
  raw_metadata_reference text NOT NULL,
  checksum text NOT NULL,
  ingested_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  UNIQUE (tenant_id, property_id, provider_id, collection_id, external_item_id),
  FOREIGN KEY (tenant_id, property_id) REFERENCES property(tenant_id, id),
  FOREIGN KEY (provider_id, collection_id)
    REFERENCES geospatial_collection(provider_id, external_collection_id),
  CHECK (cloud_cover IS NULL OR cloud_cover BETWEEN 0 AND 100)
);
CREATE INDEX IF NOT EXISTS satellite_scene_property_idx
  ON satellite_scene (tenant_id, property_id, acquisition_datetime DESC);
CREATE INDEX IF NOT EXISTS satellite_scene_geometry_gix
  ON satellite_scene USING gist (geometry);

ALTER TABLE satellite_search
  ADD CONSTRAINT satellite_search_selected_scene_fk
  FOREIGN KEY (tenant_id, selected_scene_id)
  REFERENCES satellite_scene(tenant_id, id);

CREATE TABLE IF NOT EXISTS satellite_asset (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  scene_id uuid NOT NULL,
  asset_key text NOT NULL,
  href text NOT NULL,
  media_type text,
  roles jsonb NOT NULL DEFAULT '[]'::jsonb,
  title text,
  band_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  download_policy text NOT NULL DEFAULT 'METADATA_ONLY',
  checksum text,
  size_bytes bigint,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  UNIQUE (tenant_id, scene_id, asset_key),
  FOREIGN KEY (tenant_id, scene_id) REFERENCES satellite_scene(tenant_id, id),
  CHECK (size_bytes IS NULL OR size_bytes >= 0)
);

CREATE TABLE IF NOT EXISTS satellite_search_candidate (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  search_id uuid NOT NULL,
  scene_id uuid NOT NULL,
  rank integer NOT NULL,
  selected boolean NOT NULL DEFAULT false,
  rejection_reason text,
  criteria jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  UNIQUE (tenant_id, search_id, scene_id),
  FOREIGN KEY (tenant_id, search_id) REFERENCES satellite_search(tenant_id, id),
  FOREIGN KEY (tenant_id, scene_id) REFERENCES satellite_scene(tenant_id, id),
  CHECK (rank >= 1)
);

CREATE TABLE IF NOT EXISTS processing_job (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  property_id uuid NOT NULL,
  scene_id uuid NOT NULL,
  job_type text NOT NULL,
  algorithm_id text NOT NULL,
  algorithm_version text NOT NULL,
  parameters jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL,
  idempotency_key text NOT NULL,
  output_product_id uuid,
  failure_reason text,
  created_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz,
  finished_at timestamptz,
  UNIQUE (tenant_id, id),
  UNIQUE (tenant_id, idempotency_key),
  FOREIGN KEY (tenant_id, property_id) REFERENCES property(tenant_id, id),
  FOREIGN KEY (tenant_id, scene_id) REFERENCES satellite_scene(tenant_id, id)
);

CREATE TABLE IF NOT EXISTS derived_product (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  property_id uuid NOT NULL,
  scene_id uuid NOT NULL,
  processing_job_id uuid NOT NULL,
  product_type text NOT NULL,
  data_classification text NOT NULL,
  valid_count bigint NOT NULL,
  nodata_count bigint NOT NULL,
  minimum numeric(20,10),
  maximum numeric(20,10),
  mean numeric(20,10),
  median numeric(20,10),
  coverage_percentage numeric(10,6),
  output_reference text,
  output_checksum text,
  algorithm_id text NOT NULL,
  algorithm_version text NOT NULL,
  formula text NOT NULL,
  input_asset_keys jsonb NOT NULL DEFAULT '[]'::jsonb,
  parameters jsonb NOT NULL DEFAULT '{}'::jsonb,
  limitations jsonb NOT NULL DEFAULT '[]'::jsonb,
  quality jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  UNIQUE (tenant_id, processing_job_id),
  FOREIGN KEY (tenant_id, property_id) REFERENCES property(tenant_id, id),
  FOREIGN KEY (tenant_id, scene_id) REFERENCES satellite_scene(tenant_id, id),
  FOREIGN KEY (tenant_id, processing_job_id) REFERENCES processing_job(tenant_id, id),
  CHECK (valid_count >= 0),
  CHECK (nodata_count >= 0),
  CHECK (coverage_percentage IS NULL OR coverage_percentage BETWEEN 0 AND 100)
);

ALTER TABLE processing_job
  ADD CONSTRAINT processing_job_output_product_fk
  FOREIGN KEY (tenant_id, output_product_id)
  REFERENCES derived_product(tenant_id, id);

CREATE OR REPLACE FUNCTION enforce_evidence_reference_tenant()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  referenced_tenant uuid;
BEGIN
  IF NEW.evidence_type = 'OBSERVATION' THEN
    SELECT tenant_id INTO referenced_tenant FROM observation WHERE id = NEW.reference_id;
  ELSIF NEW.evidence_type = 'PROPERTY' THEN
    SELECT tenant_id INTO referenced_tenant FROM property WHERE id = NEW.reference_id;
  ELSIF NEW.evidence_type = 'DECISION' THEN
    SELECT tenant_id INTO referenced_tenant FROM decision WHERE id = NEW.reference_id;
  ELSIF NEW.evidence_type = 'SATELLITE_SCENE' THEN
    SELECT tenant_id INTO referenced_tenant FROM satellite_scene WHERE id = NEW.reference_id;
  ELSIF NEW.evidence_type = 'DERIVED_PRODUCT' THEN
    SELECT tenant_id INTO referenced_tenant FROM derived_product WHERE id = NEW.reference_id;
  ELSE
    RAISE EXCEPTION 'unsupported evidence reference type: %', NEW.evidence_type USING ERRCODE = 'check_violation';
  END IF;
  IF referenced_tenant IS NULL OR referenced_tenant <> NEW.tenant_id THEN
    RAISE EXCEPTION 'evidence reference crosses tenant boundary' USING ERRCODE = 'foreign_key_violation';
  END IF;
  RETURN NEW;
END;
$$;

DO $$
DECLARE item record;
BEGIN
  FOR item IN SELECT table_name FROM (VALUES
    ('satellite_search'), ('satellite_scene'), ('satellite_asset'),
    ('satellite_search_candidate'), ('processing_job'), ('derived_product')
  ) AS tables(table_name)
  LOOP
    EXECUTE format('CREATE POLICY %I ON %I USING (tenant_id::text = current_setting(''app.tenant_id'', true) OR current_setting(''app.platform_admin'', true) = ''true'') WITH CHECK (tenant_id::text = current_setting(''app.tenant_id'', true) OR current_setting(''app.platform_admin'', true) = ''true'')', item.table_name || '_tenant_isolation', item.table_name);
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', item.table_name);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', item.table_name);
  END LOOP;
END $$;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ribeira_app;

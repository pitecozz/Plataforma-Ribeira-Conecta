-- Phase 1P.5C: globally scoped, evidence-first SAR flood pilot products.
-- These records are deliberately not tenant properties or customer exposure.

CREATE TABLE event_analysis_aoi (
  id uuid PRIMARY KEY,
  event_id uuid NOT NULL REFERENCES operational_event(id),
  municipality_id uuid NOT NULL REFERENCES municipality_reference(id),
  aoi_key text NOT NULL UNIQUE,
  geometry geometry(Geometry,4674) NOT NULL,
  geometry_checksum text NOT NULL CHECK (geometry_checksum ~ '^[0-9a-f]{64}$'),
  source_reference text NOT NULL,
  classification text NOT NULL CHECK (classification = 'DERIVED'),
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(event_id, municipality_id)
);

CREATE TABLE event_analysis_aoi_evidence (
  id uuid PRIMARY KEY,
  aoi_id uuid NOT NULL REFERENCES event_analysis_aoi(id) ON DELETE CASCADE,
  evidence_type text NOT NULL CHECK (evidence_type = 'EVENT_PRIORITY'),
  source_reference text NOT NULL,
  observed_at timestamptz,
  retrieved_at timestamptz NOT NULL,
  classification text NOT NULL CHECK (classification = 'OFFICIAL_SOURCE'),
  detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(aoi_id, evidence_type, source_reference)
);

CREATE TABLE event_sar_tile (
  id uuid PRIMARY KEY,
  aoi_id uuid NOT NULL REFERENCES event_analysis_aoi(id) ON DELETE CASCADE,
  tile_key text NOT NULL,
  geometry geometry(Polygon,4674) NOT NULL,
  grid_crs text NOT NULL,
  grid_transform jsonb NOT NULL,
  width integer NOT NULL CHECK (width > 0),
  height integer NOT NULL CHECK (height > 0),
  pixel_size_m numeric NOT NULL CHECK (pixel_size_m > 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(aoi_id, tile_key)
);
CREATE INDEX event_sar_tile_aoi_idx ON event_sar_tile(aoi_id, tile_key);
CREATE INDEX event_sar_tile_geometry_gix ON event_sar_tile USING gist(geometry);

CREATE TABLE event_sar_asset (
  id uuid PRIMARY KEY,
  tile_id uuid NOT NULL REFERENCES event_sar_tile(id) ON DELETE CASCADE,
  scene_evidence_id uuid NOT NULL REFERENCES satellite_event_scene_evidence(id),
  acquisition_role text NOT NULL CHECK (acquisition_role IN ('PRE','EVENT')),
  asset_type text NOT NULL CHECK (asset_type IN (
    'VV_RTC_LINEAR_POWER','VH_RTC_LINEAR_POWER','DATA_MASK','SHADOW_MASK',
    'LOCAL_INCIDENCE_ANGLE','VV_DB','VH_DB','EVENT_WATER_SIGNAL',
    'PERMANENT_WATER_MASK','TEMPORARY_OPEN_WATER_CANDIDATE_RAW',
    'TEMPORARY_OPEN_WATER_CANDIDATE_CLEAN'
  )),
  storage_reference text NOT NULL,
  sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tile_id, scene_evidence_id, asset_type)
);
CREATE INDEX event_sar_asset_tile_idx ON event_sar_asset(tile_id, acquisition_role, asset_type);

CREATE TABLE event_flood_analysis (
  id uuid PRIMARY KEY,
  aoi_id uuid NOT NULL UNIQUE REFERENCES event_analysis_aoi(id) ON DELETE CASCADE,
  status text NOT NULL CHECK (status IN ('PREPARED','SUCCEEDED','FAILED','INCONCLUSIVE')),
  evidence_status text NOT NULL CHECK (evidence_status IN ('UNKNOWN','INCONCLUSIVE','PARTIALLY_SUPPORTED','SUPPORTED')),
  method text,
  parameters jsonb NOT NULL DEFAULT '{}'::jsonb,
  metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
  limitations jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE operational_event_timeline_entry
  DROP CONSTRAINT operational_event_timeline_entry_event_type_check;
ALTER TABLE operational_event_timeline_entry
  ADD CONSTRAINT operational_event_timeline_entry_event_type_check
  CHECK (event_type IN (
    'RAINFALL_OBSERVATION','RAINFALL_ACCUMULATION_PEAK','RESERVOIR_OPERATION',
    'CLIMATE_CONTEXT','SATELLITE_ACQUISITION','FLOOD_EXTENT','SAR_RTC_PREPARED',
    'SAR_CHANGE_ANALYSIS','TEMPORARY_OPEN_WATER_CANDIDATE'
  ));

DO $$
DECLARE item record;
BEGIN
  FOR item IN SELECT * FROM (VALUES
    ('event_analysis_aoi','event_analysis_aoi_global_access'),
    ('event_analysis_aoi_evidence','event_analysis_aoi_evidence_global_access'),
    ('event_sar_tile','event_sar_tile_global_access'),
    ('event_sar_asset','event_sar_asset_global_access'),
    ('event_flood_analysis','event_flood_analysis_global_access')
  ) AS valueset(table_name,policy_name)
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',item.table_name);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',item.table_name);
    EXECUTE format('CREATE POLICY %I ON %I FOR ALL TO ribeira_app USING (true) WITH CHECK (true)',item.policy_name,item.table_name);
  END LOOP;
END $$;

GRANT SELECT,INSERT,UPDATE,DELETE ON
  event_analysis_aoi,event_analysis_aoi_evidence,event_sar_tile,event_sar_asset,event_flood_analysis
TO ribeira_app;

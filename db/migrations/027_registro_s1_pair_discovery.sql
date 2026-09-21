-- Phase 1P.5I: catalogue-only Sentinel-1 pair discovery.  These records do
-- not assert a flood extent and must precede any Process API work.
CREATE TABLE event_sar_scene_assessment (
  id uuid PRIMARY KEY,
  aoi_id uuid NOT NULL REFERENCES event_analysis_aoi(id) ON DELETE CASCADE,
  scene_evidence_id uuid NOT NULL REFERENCES satellite_event_scene_evidence(id),
  registro_coverage_km2 numeric NOT NULL CHECK (registro_coverage_km2 >= 0),
  registro_coverage_percent numeric NOT NULL CHECK (registro_coverage_percent >= 0 AND registro_coverage_percent <= 100),
  pre_classification text NOT NULL CHECK (pre_classification IN ('GOOD_PRE','POSSIBLE_PRE','POOR_PRE','REJECTED','NOT_APPLICABLE')),
  event_classification text NOT NULL CHECK (event_classification IN ('GOOD_EVENT','POSSIBLE_EVENT','POOR_EVENT','REJECTED','NOT_APPLICABLE')),
  assessment jsonb NOT NULL DEFAULT '{}'::jsonb,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(aoi_id, scene_evidence_id)
);

CREATE TABLE event_sar_pair_selection (
  id uuid PRIMARY KEY,
  aoi_id uuid NOT NULL REFERENCES event_analysis_aoi(id) ON DELETE CASCADE,
  pair_key text NOT NULL,
  pre_scene_evidence_id uuid NOT NULL REFERENCES satellite_event_scene_evidence(id),
  event_scene_evidence_id uuid NOT NULL REFERENCES satellite_event_scene_evidence(id),
  status text NOT NULL CHECK (status IN ('CANDIDATE','SELECTED','NO_SPATIAL_COVERAGE','REJECTED')),
  common_geometry geometry(Geometry,4674),
  pre_registro_coverage_km2 numeric NOT NULL CHECK (pre_registro_coverage_km2 >= 0),
  event_registro_coverage_km2 numeric NOT NULL CHECK (event_registro_coverage_km2 >= 0),
  common_registro_coverage_km2 numeric NOT NULL CHECK (common_registro_coverage_km2 >= 0),
  common_registro_coverage_percent numeric NOT NULL CHECK (common_registro_coverage_percent >= 0 AND common_registro_coverage_percent <= 100),
  rank_order integer,
  selection_reason text NOT NULL,
  compatibility jsonb NOT NULL DEFAULT '{}'::jsonb,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(aoi_id, pair_key)
);
CREATE INDEX event_sar_pair_selection_aoi_status_idx ON event_sar_pair_selection(aoi_id,status,rank_order);

ALTER TABLE event_sar_scene_assessment ENABLE ROW LEVEL SECURITY;
ALTER TABLE event_sar_scene_assessment FORCE ROW LEVEL SECURITY;
CREATE POLICY event_sar_scene_assessment_global_access ON event_sar_scene_assessment
  FOR ALL TO ribeira_app USING (true) WITH CHECK (true);
ALTER TABLE event_sar_pair_selection ENABLE ROW LEVEL SECURITY;
ALTER TABLE event_sar_pair_selection FORCE ROW LEVEL SECURITY;
CREATE POLICY event_sar_pair_selection_global_access ON event_sar_pair_selection
  FOR ALL TO ribeira_app USING (true) WITH CHECK (true);
GRANT SELECT,INSERT,UPDATE,DELETE ON event_sar_scene_assessment,event_sar_pair_selection TO ribeira_app;

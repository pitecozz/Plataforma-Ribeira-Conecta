-- Phase 1P.5: distinguish ignored WIS2 records from rejected records.
ALTER TABLE hydro_ingestion_run
  ADD COLUMN target_candidates integer NOT NULL DEFAULT 0 CHECK (target_candidates >= 0),
  ADD COLUMN observations_ignored integer NOT NULL DEFAULT 0 CHECK (observations_ignored >= 0),
  ADD COLUMN quality_reason_counts jsonb NOT NULL DEFAULT '{}'::jsonb;

-- Prior collector versions used invalid_observations for records outside the
-- verified Vale scope or with a null source value.  Retain the count, but make
-- the historical classification explicit instead of representing it as a data
-- quality rejection.
UPDATE hydro_ingestion_run
   SET observations_ignored = invalid_observations,
       invalid_observations = 0,
       quality_reason_counts = jsonb_build_object(
         'LEGACY_IGNORED_SCOPE_OR_MISSING_VALUE', invalid_observations
       )
 WHERE provider = 'INMET_WIS2'
   AND invalid_observations > 0;

CREATE TABLE satellite_event_scene_evidence (
  id uuid PRIMARY KEY,
  event_id uuid NOT NULL REFERENCES operational_event(id),
  provider text NOT NULL,
  collection_id text NOT NULL,
  provider_record_id text NOT NULL,
  acquired_at timestamptz NOT NULL,
  geometry geometry(Geometry,4326) NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  source_reference text NOT NULL,
  classification text NOT NULL CHECK (classification IN ('OFFICIAL_SOURCE','DERIVED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(event_id,provider,collection_id,provider_record_id)
);

ALTER TABLE operational_event_timeline_entry
  DROP CONSTRAINT operational_event_timeline_entry_event_type_check;
ALTER TABLE operational_event_timeline_entry
  ADD CONSTRAINT operational_event_timeline_entry_event_type_check
  CHECK (event_type IN ('RAINFALL_OBSERVATION','RAINFALL_ACCUMULATION_PEAK','RESERVOIR_OPERATION','CLIMATE_CONTEXT','SATELLITE_ACQUISITION','FLOOD_EXTENT'));

ALTER TABLE satellite_event_scene_evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE satellite_event_scene_evidence FORCE ROW LEVEL SECURITY;
CREATE POLICY satellite_event_scene_evidence_global_access ON satellite_event_scene_evidence
  FOR ALL TO ribeira_app USING (true) WITH CHECK (true);
GRANT SELECT,INSERT,UPDATE,DELETE ON satellite_event_scene_evidence TO ribeira_app;

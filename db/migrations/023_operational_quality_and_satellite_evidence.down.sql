DO $$ BEGIN
 IF EXISTS (SELECT 1 FROM satellite_event_scene_evidence) THEN
  RAISE EXCEPTION 'cannot rollback 023 after satellite event evidence has been stored';
 END IF;
END $$;
DROP POLICY satellite_event_scene_evidence_global_access ON satellite_event_scene_evidence;
DROP TABLE satellite_event_scene_evidence;
ALTER TABLE operational_event_timeline_entry
  DROP CONSTRAINT operational_event_timeline_entry_event_type_check;
ALTER TABLE operational_event_timeline_entry
  ADD CONSTRAINT operational_event_timeline_entry_event_type_check
  CHECK (event_type IN ('RAINFALL_OBSERVATION','RAINFALL_ACCUMULATION_PEAK','RESERVOIR_OPERATION','CLIMATE_CONTEXT'));
ALTER TABLE hydro_ingestion_run
  DROP COLUMN quality_reason_counts,
  DROP COLUMN observations_ignored,
  DROP COLUMN target_candidates;

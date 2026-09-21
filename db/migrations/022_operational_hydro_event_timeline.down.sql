DO $$ BEGIN
 IF EXISTS (SELECT 1 FROM hydro_ingestion_run)
    OR EXISTS (SELECT 1 FROM operational_event)
    OR EXISTS (SELECT 1 FROM operational_event_evidence)
    OR EXISTS (SELECT 1 FROM operational_event_timeline_entry) THEN
  RAISE EXCEPTION 'cannot rollback 022 after operational hydro evidence has been stored';
 END IF;
END $$;
DROP TABLE operational_event_timeline_entry;
DROP TABLE operational_event_evidence;
DROP TABLE operational_event;
DROP TABLE hydro_ingestion_run;

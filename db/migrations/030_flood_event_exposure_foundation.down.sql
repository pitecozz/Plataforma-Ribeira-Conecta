DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM tenant_flood_exposure_assessment)
     OR EXISTS (SELECT 1 FROM flood_event_exposure_zone)
     OR EXISTS (SELECT 1 FROM flood_event_municipality_context)
     OR EXISTS (SELECT 1 FROM flood_event_hypothesis_evidence) THEN
    RAISE EXCEPTION 'cannot rollback 030 after flood exposure evidence has been stored';
  END IF;
END $$;
DROP TRIGGER flood_event_exposure_zone_updated_at ON flood_event_exposure_zone;
DROP TRIGGER tenant_flood_exposure_assessment_subject_tenant_check ON tenant_flood_exposure_assessment;
DROP TABLE tenant_flood_exposure_assessment;
DROP TABLE flood_event_municipality_context;
DROP TABLE flood_event_exposure_zone;
DROP TABLE flood_event_hypothesis_evidence;
DROP TABLE flood_event_hypothesis;
DROP TABLE flood_event_profile;
DROP FUNCTION flood_exposure_subject_tenant_check;

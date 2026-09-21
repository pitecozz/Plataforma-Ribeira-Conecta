DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM event_sar_scene_assessment)
     OR EXISTS (SELECT 1 FROM event_sar_pair_selection) THEN
    RAISE EXCEPTION 'cannot rollback 027 after Sentinel-1 pair discovery has been stored';
  END IF;
END $$;
DROP POLICY event_sar_pair_selection_global_access ON event_sar_pair_selection;
DROP POLICY event_sar_scene_assessment_global_access ON event_sar_scene_assessment;
DROP TABLE event_sar_pair_selection;
DROP TABLE event_sar_scene_assessment;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM event_analysis_aoi)
     OR EXISTS (SELECT 1 FROM event_analysis_aoi_evidence)
     OR EXISTS (SELECT 1 FROM event_sar_tile)
     OR EXISTS (SELECT 1 FROM event_sar_asset)
     OR EXISTS (SELECT 1 FROM event_flood_analysis) THEN
    RAISE EXCEPTION 'cannot rollback 025 after event SAR pilot evidence has been stored';
  END IF;
END $$;

DROP POLICY event_flood_analysis_global_access ON event_flood_analysis;
DROP POLICY event_sar_asset_global_access ON event_sar_asset;
DROP POLICY event_sar_tile_global_access ON event_sar_tile;
DROP POLICY event_analysis_aoi_evidence_global_access ON event_analysis_aoi_evidence;
DROP POLICY event_analysis_aoi_global_access ON event_analysis_aoi;
DROP TABLE event_flood_analysis;
DROP TABLE event_sar_asset;
DROP TABLE event_sar_tile;
DROP TABLE event_analysis_aoi_evidence;
DROP TABLE event_analysis_aoi;

ALTER TABLE operational_event_timeline_entry
  DROP CONSTRAINT operational_event_timeline_entry_event_type_check;
ALTER TABLE operational_event_timeline_entry
  ADD CONSTRAINT operational_event_timeline_entry_event_type_check
  CHECK (event_type IN (
    'RAINFALL_OBSERVATION','RAINFALL_ACCUMULATION_PEAK','RESERVOIR_OPERATION',
    'CLIMATE_CONTEXT','SATELLITE_ACQUISITION','FLOOD_EXTENT'
  ));

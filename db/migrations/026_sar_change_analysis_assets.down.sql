DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM event_sar_asset WHERE asset_type IN ('DELTA_VV_DB','DELTA_VH_DB','JRC_SEASONALITY')) THEN
    RAISE EXCEPTION 'cannot rollback 026 after derived SAR change assets have been stored';
  END IF;
END $$;
ALTER TABLE event_sar_asset DROP CONSTRAINT event_sar_asset_asset_type_check;
ALTER TABLE event_sar_asset ADD CONSTRAINT event_sar_asset_asset_type_check CHECK (asset_type IN (
  'VV_RTC_LINEAR_POWER','VH_RTC_LINEAR_POWER','DATA_MASK','SHADOW_MASK',
  'LOCAL_INCIDENCE_ANGLE','VV_DB','VH_DB','EVENT_WATER_SIGNAL',
  'PERMANENT_WATER_MASK','TEMPORARY_OPEN_WATER_CANDIDATE_RAW',
  'TEMPORARY_OPEN_WATER_CANDIDATE_CLEAN'
));

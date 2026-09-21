DO $$ BEGIN
 IF EXISTS (SELECT 1 FROM hydrological_observation WHERE provider_record_id IS NOT NULL)
    OR EXISTS (SELECT 1 FROM banana_municipal_baseline WHERE category_id IS NOT NULL)
    OR EXISTS (SELECT 1 FROM spatial_scope_municipality) THEN
  RAISE EXCEPTION 'cannot rollback 021 after WIS2, banana, or scope membership data has been stored';
 END IF;
END $$;

DROP INDEX hydrological_observation_provider_record_identity;
ALTER TABLE hydrological_observation
  DROP CONSTRAINT hydrological_observation_period_complete,
  DROP COLUMN provenance,
  DROP COLUMN normalized_unit,
  DROP COLUMN normalized_value,
  DROP COLUMN raw_unit,
  DROP COLUMN delivery_channel,
  DROP COLUMN provider_record_id,
  DROP COLUMN period_end,
  DROP COLUMN period_start;
ALTER TABLE banana_municipal_baseline
  DROP COLUMN data_status,
  DROP COLUMN raw_values,
  DROP COLUMN category_label,
  DROP COLUMN category_id,
  DROP COLUMN classification_label,
  DROP COLUMN classification_id;

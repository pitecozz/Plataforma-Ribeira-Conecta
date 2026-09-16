ALTER TABLE observation
  ALTER COLUMN original_observation_timestamp TYPE timestamptz
  USING NULLIF(original_observation_timestamp, '')::timestamptz;

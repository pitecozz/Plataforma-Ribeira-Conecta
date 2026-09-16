-- Preserve the provider's original timestamp representation, including offset.
ALTER TABLE observation
  ALTER COLUMN original_observation_timestamp TYPE text
  USING original_observation_timestamp::text;

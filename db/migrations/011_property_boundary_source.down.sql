-- Refuse a destructive rollback once provenance has been recorded.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM property WHERE boundary_source IS NOT NULL) THEN
    RAISE EXCEPTION 'cannot remove property.boundary_source while provenance values exist';
  END IF;
END $$;

ALTER TABLE property DROP COLUMN IF EXISTS boundary_source;

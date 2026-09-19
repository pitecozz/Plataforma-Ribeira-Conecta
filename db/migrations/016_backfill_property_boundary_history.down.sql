-- Reversible only while the backfilled baseline is the complete history.
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM property_boundary_version
    WHERE actor IS DISTINCT FROM 'migration-016' OR version <> 1
  ) THEN
    RAISE EXCEPTION 'cannot rollback 016 after boundary history has changed';
  END IF;
END $$;

DELETE FROM property_boundary_version WHERE actor = 'migration-016' AND version = 1;
UPDATE property SET boundary_checksum = NULL
WHERE boundary_checksum IS NOT NULL;

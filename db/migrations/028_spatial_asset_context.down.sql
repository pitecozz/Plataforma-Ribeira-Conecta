DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM asset WHERE geometry IS NOT NULL OR context <> '{}'::jsonb) THEN
    RAISE EXCEPTION 'cannot rollback 028 after spatial asset context has been stored';
  END IF;
END $$;
DROP INDEX asset_geometry_gix;
ALTER TABLE asset DROP CONSTRAINT asset_geometry_crs_check;
ALTER TABLE asset DROP COLUMN context;
ALTER TABLE asset DROP COLUMN observed_at;
ALTER TABLE asset DROP COLUMN source_reference;
ALTER TABLE asset DROP COLUMN geometry_crs;
ALTER TABLE asset DROP COLUMN geometry;

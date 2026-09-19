DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM property_boundary_version) THEN
    RAISE EXCEPTION 'cannot rollback 015 while boundary history exists';
  END IF;
END $$;
DROP POLICY IF EXISTS property_boundary_version_tenant_isolation ON property_boundary_version;
DROP TABLE IF EXISTS property_boundary_version;
ALTER TABLE property DROP COLUMN IF EXISTS updated_at;
ALTER TABLE property DROP COLUMN IF EXISTS boundary_checksum;

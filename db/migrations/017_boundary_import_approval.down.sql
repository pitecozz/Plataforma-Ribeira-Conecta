DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM boundary_import) THEN
    RAISE EXCEPTION 'cannot rollback 017 while boundary imports exist';
  END IF;
END $$;
DROP TRIGGER IF EXISTS boundary_import_transition_guard ON boundary_import;
DROP FUNCTION IF EXISTS boundary_import_transition_guard();
DROP POLICY IF EXISTS boundary_import_tenant_isolation ON boundary_import;
DROP TABLE IF EXISTS boundary_import;

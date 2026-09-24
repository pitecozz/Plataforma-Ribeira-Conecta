DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM rule_definition WHERE scope_type='ASSET') THEN
    RAISE EXCEPTION 'cannot rollback 037 while asset-scoped rules exist';
  END IF;
END $$;
ALTER TABLE rule_definition
  ADD CONSTRAINT rule_definition_scope_type_check
  CHECK (scope_type IN ('TENANT','PROPERTY'));

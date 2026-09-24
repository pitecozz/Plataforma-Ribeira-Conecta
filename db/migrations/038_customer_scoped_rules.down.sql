DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM rule_definition WHERE scope_type='CUSTOMER')
     OR EXISTS (SELECT 1 FROM decision WHERE selected_rule_scope_type IS NOT NULL OR subject_customer_id IS NOT NULL) THEN
    RAISE EXCEPTION 'cannot rollback 038 after customer-scoped rules or decision context have been stored';
  END IF;
END $$;

DROP TRIGGER decision_subject_customer_property_guard ON decision;
DROP FUNCTION decision_subject_customer_property_check();
ALTER TABLE decision DROP CONSTRAINT decision_rule_context_check;
ALTER TABLE decision DROP CONSTRAINT decision_subject_customer_tenant_fk;
ALTER TABLE decision DROP COLUMN subject_customer_id;
ALTER TABLE decision DROP COLUMN selected_rule_scope_type;

ALTER TABLE rule_definition DROP CONSTRAINT rule_definition_scope_check;
ALTER TABLE rule_definition DROP CONSTRAINT rule_definition_scope_customer_tenant_fk;
DROP INDEX rule_definition_scope_idx;
ALTER TABLE rule_definition DROP COLUMN scope_customer_id;
ALTER TABLE rule_definition ADD CONSTRAINT rule_definition_scope_check CHECK (
  (scope_type='TENANT' AND scope_property_id IS NULL AND scope_asset_id IS NULL)
  OR (scope_type='PROPERTY' AND scope_property_id IS NOT NULL AND scope_asset_id IS NULL)
  OR (scope_type='ASSET' AND scope_property_id IS NULL AND scope_asset_id IS NOT NULL)
);
CREATE INDEX rule_definition_scope_idx
  ON rule_definition(
    tenant_id,metric,status,scope_type,scope_property_id,scope_asset_id,version DESC
  );

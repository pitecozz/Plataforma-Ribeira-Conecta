-- Field/talhao-scoped rules are explicit, tenant-bound operational context.
-- They do not turn a field geometry into legal, crop, soil or agronomic evidence.
ALTER TABLE rule_definition DROP CONSTRAINT rule_definition_scope_check;
ALTER TABLE rule_definition
  ADD COLUMN scope_field_id uuid,
  ADD CONSTRAINT rule_definition_scope_field_tenant_fk
    FOREIGN KEY (tenant_id, scope_field_id) REFERENCES field_context(tenant_id, id),
  ADD CONSTRAINT rule_definition_scope_check CHECK (
    (scope_type='TENANT' AND scope_property_id IS NULL AND scope_asset_id IS NULL AND scope_field_id IS NULL AND scope_customer_id IS NULL)
    OR (scope_type='PROPERTY' AND scope_property_id IS NOT NULL AND scope_asset_id IS NULL AND scope_field_id IS NULL AND scope_customer_id IS NULL)
    OR (scope_type='ASSET' AND scope_property_id IS NULL AND scope_asset_id IS NOT NULL AND scope_field_id IS NULL AND scope_customer_id IS NULL)
    OR (scope_type='FIELD' AND scope_property_id IS NULL AND scope_asset_id IS NULL AND scope_field_id IS NOT NULL AND scope_customer_id IS NULL)
    OR (scope_type='CUSTOMER' AND scope_property_id IS NULL AND scope_asset_id IS NULL AND scope_field_id IS NULL AND scope_customer_id IS NOT NULL)
  );
DROP INDEX rule_definition_scope_idx;
CREATE INDEX rule_definition_scope_idx
  ON rule_definition(
    tenant_id,metric,status,scope_type,scope_property_id,scope_asset_id,scope_field_id,scope_customer_id,version DESC
  );

ALTER TABLE decision DROP CONSTRAINT decision_rule_context_check;
ALTER TABLE decision
  ADD COLUMN subject_field_id uuid,
  ADD CONSTRAINT decision_subject_field_tenant_fk
    FOREIGN KEY (tenant_id, subject_field_id) REFERENCES field_context(tenant_id, id),
  ADD CONSTRAINT decision_rule_context_check CHECK (
    (selected_rule_scope_type IS NULL AND subject_customer_id IS NULL)
    OR (selected_rule_scope_type='CUSTOMER' AND subject_customer_id IS NOT NULL)
    OR (selected_rule_scope_type='FIELD' AND subject_customer_id IS NULL AND subject_field_id IS NOT NULL)
    OR (selected_rule_scope_type IN ('TENANT','PROPERTY','ASSET') AND subject_customer_id IS NULL)
  );

CREATE OR REPLACE FUNCTION decision_subject_field_property_check()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  IF NEW.subject_field_id IS NOT NULL AND NOT EXISTS (
    SELECT 1
      FROM field_context
     WHERE id=NEW.subject_field_id
       AND tenant_id=NEW.tenant_id
       AND property_id=NEW.property_id
  ) THEN
    RAISE EXCEPTION 'decision subject field must belong to the decision property in the tenant'
      USING ERRCODE = 'foreign_key_violation';
  END IF;
  RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION decision_subject_field_property_check() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION decision_subject_field_property_check() TO ribeira_app;
CREATE TRIGGER decision_subject_field_property_guard
  BEFORE INSERT OR UPDATE OF tenant_id,property_id,subject_field_id ON decision
  FOR EACH ROW EXECUTE FUNCTION decision_subject_field_property_check();

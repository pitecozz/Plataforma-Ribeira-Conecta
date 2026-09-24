-- Customer rules are applicable only through a current, tenant-local customer/property link.
-- They are not proof of ownership, need, availability or an agronomic conclusion.
ALTER TABLE rule_definition DROP CONSTRAINT rule_definition_scope_check;
ALTER TABLE rule_definition
  ADD COLUMN scope_customer_id uuid,
  ADD CONSTRAINT rule_definition_scope_customer_tenant_fk
    FOREIGN KEY (tenant_id, scope_customer_id) REFERENCES customer(tenant_id, id),
  ADD CONSTRAINT rule_definition_scope_check CHECK (
    (scope_type='TENANT' AND scope_property_id IS NULL AND scope_asset_id IS NULL AND scope_customer_id IS NULL)
    OR (scope_type='PROPERTY' AND scope_property_id IS NOT NULL AND scope_asset_id IS NULL AND scope_customer_id IS NULL)
    OR (scope_type='ASSET' AND scope_property_id IS NULL AND scope_asset_id IS NOT NULL AND scope_customer_id IS NULL)
    OR (scope_type='CUSTOMER' AND scope_property_id IS NULL AND scope_asset_id IS NULL AND scope_customer_id IS NOT NULL)
  );
DROP INDEX rule_definition_scope_idx;
CREATE INDEX rule_definition_scope_idx
  ON rule_definition(
    tenant_id,metric,status,scope_type,scope_property_id,scope_asset_id,scope_customer_id,version DESC
  );

-- Snapshot selected applicability context. The decision remains property-bound;
-- a customer ID is valid only for an explicitly customer-scoped selection.
ALTER TABLE decision
  ADD COLUMN selected_rule_scope_type text,
  ADD COLUMN subject_customer_id uuid,
  ADD CONSTRAINT decision_subject_customer_tenant_fk
    FOREIGN KEY (tenant_id, subject_customer_id) REFERENCES customer(tenant_id, id),
  ADD CONSTRAINT decision_rule_context_check CHECK (
    (selected_rule_scope_type IS NULL AND subject_customer_id IS NULL)
    OR (selected_rule_scope_type='CUSTOMER' AND subject_customer_id IS NOT NULL)
    OR (selected_rule_scope_type IN ('TENANT','PROPERTY','ASSET') AND subject_customer_id IS NULL)
  );

CREATE OR REPLACE FUNCTION decision_subject_customer_property_check()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  IF NEW.subject_customer_id IS NOT NULL AND NOT EXISTS (
    SELECT 1
      FROM customer_property
     WHERE tenant_id=NEW.tenant_id
       AND customer_id=NEW.subject_customer_id
       AND property_id=NEW.property_id
       AND valid_from <= now()
       AND (valid_until IS NULL OR now() < valid_until)
  ) THEN
    RAISE EXCEPTION 'decision subject customer requires an active tenant-local customer/property link'
      USING ERRCODE = 'foreign_key_violation';
  END IF;
  RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION decision_subject_customer_property_check() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION decision_subject_customer_property_check() TO ribeira_app;
CREATE TRIGGER decision_subject_customer_property_guard
  BEFORE INSERT OR UPDATE OF tenant_id,property_id,subject_customer_id ON decision
  FOR EACH ROW EXECUTE FUNCTION decision_subject_customer_property_check();

-- Explicit scope prevents a rule from silently applying to an unrelated property.
ALTER TABLE rule_definition
  ADD COLUMN scope_type text NOT NULL DEFAULT 'TENANT' CHECK (scope_type IN ('TENANT','PROPERTY')),
  ADD COLUMN scope_property_id uuid REFERENCES property(id),
  ADD CONSTRAINT rule_definition_scope_check CHECK (
    (scope_type='TENANT' AND scope_property_id IS NULL)
    OR (scope_type='PROPERTY' AND scope_property_id IS NOT NULL)
  );
CREATE INDEX rule_definition_scope_idx
  ON rule_definition(tenant_id,metric,status,scope_type,scope_property_id,version DESC);

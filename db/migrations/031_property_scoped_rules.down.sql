ALTER TABLE rule_definition DROP CONSTRAINT rule_definition_scope_check;
DROP INDEX rule_definition_scope_idx;
ALTER TABLE rule_definition DROP COLUMN scope_property_id, DROP COLUMN scope_type;

-- Migration 031 created this inline CHECK separately from the named scope
-- consistency constraint.  Keep the successor forward-only: 036 supplies the
-- complete ASSET consistency rule, while this removes the obsolete type list.
ALTER TABLE rule_definition
  DROP CONSTRAINT rule_definition_scope_type_check;

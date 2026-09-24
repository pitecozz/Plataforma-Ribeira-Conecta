-- Preserve field/talhão geometry history. Corrections are future versions, never rewrites.
CREATE OR REPLACE FUNCTION field_context_boundary_version_immutable()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  RAISE EXCEPTION 'field context boundary versions are immutable; create a successor version instead'
    USING ERRCODE = 'integrity_constraint_violation';
END;
$$;
REVOKE ALL ON FUNCTION field_context_boundary_version_immutable() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION field_context_boundary_version_immutable() TO ribeira_app;
CREATE TRIGGER field_context_boundary_version_immutable
  BEFORE UPDATE OR DELETE ON field_context_boundary_version
  FOR EACH ROW EXECUTE FUNCTION field_context_boundary_version_immutable();


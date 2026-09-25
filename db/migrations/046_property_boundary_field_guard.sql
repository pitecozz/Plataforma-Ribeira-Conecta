CREATE OR REPLACE FUNCTION field_context_boundary_property_guard()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  PERFORM pg_advisory_xact_lock(
    hashtextextended(NEW.tenant_id::text || ':' || NEW.property_id::text, 0)
  );

  IF ST_SRID(NEW.geometry) <> 4326
     OR GeometryType(NEW.geometry) NOT IN ('POLYGON','MULTIPOLYGON')
     OR NOT ST_IsValid(NEW.geometry) THEN
    RAISE EXCEPTION 'field context geometry must be a valid EPSG:4326 Polygon or MultiPolygon'
      USING ERRCODE = 'check_violation';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM property
     WHERE tenant_id=NEW.tenant_id
       AND id=NEW.property_id
       AND geometry IS NOT NULL
       AND ST_Covers(geometry, NEW.geometry)
  ) THEN
    RAISE EXCEPTION 'field context geometry must be contained by a persisted tenant property boundary'
      USING ERRCODE = 'foreign_key_violation';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM field_context
     WHERE tenant_id=NEW.tenant_id
       AND id=NEW.field_context_id
       AND property_id=NEW.property_id
  ) THEN
    RAISE EXCEPTION 'field context boundary must match its tenant property'
      USING ERRCODE = 'foreign_key_violation';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION property_boundary_field_guard()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  IF NEW.geometry IS NOT DISTINCT FROM OLD.geometry THEN
    RETURN NEW;
  END IF;

  PERFORM pg_advisory_xact_lock(
    hashtextextended(NEW.tenant_id::text || ':' || NEW.id::text, 0)
  );

  IF EXISTS (
    SELECT 1
    FROM field_context AS field
    JOIN field_context_boundary_version AS version
      ON version.tenant_id = field.tenant_id
     AND version.field_context_id = field.id
     AND version.version = (
       SELECT max(latest.version)
       FROM field_context_boundary_version AS latest
       WHERE latest.tenant_id = field.tenant_id
         AND latest.field_context_id = field.id
     )
    WHERE field.tenant_id = NEW.tenant_id
      AND field.property_id = NEW.id
      AND NOT ST_Covers(NEW.geometry, version.geometry)
  ) THEN
    RAISE EXCEPTION 'property boundary must cover every current field boundary'
      USING ERRCODE = 'check_violation';
  END IF;

  RETURN NEW;
END
$$;

CREATE TRIGGER property_boundary_field_guard
BEFORE UPDATE OF geometry ON property
FOR EACH ROW EXECUTE FUNCTION property_boundary_field_guard();

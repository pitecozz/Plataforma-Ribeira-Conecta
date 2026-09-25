DROP TRIGGER property_boundary_field_guard ON property;
DROP FUNCTION property_boundary_field_guard();

CREATE OR REPLACE FUNCTION field_context_boundary_property_guard()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
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

-- Rollback is intentionally refused after any hydro fact has been stored.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM hydrological_station)
     OR EXISTS (SELECT 1 FROM hydrological_observation)
     OR EXISTS (SELECT 1 FROM source_health)
     OR EXISTS (SELECT 1 FROM reservoir)
     OR EXISTS (SELECT 1 FROM reservoir_operation_event)
     OR EXISTS (SELECT 1 FROM climate_context)
     OR EXISTS (SELECT 1 FROM hydro_hypothesis)
     OR EXISTS (SELECT 1 FROM hydro_hypothesis_evidence) THEN
    RAISE EXCEPTION 'cannot rollback 019 after hydrology records have been stored';
  END IF;
END;
$$;

DROP TRIGGER IF EXISTS hydro_hypothesis_updated_at ON hydro_hypothesis;
DROP TRIGGER IF EXISTS reservoir_updated_at ON reservoir;
DROP TRIGGER IF EXISTS hydrological_station_updated_at ON hydrological_station;
DROP TRIGGER IF EXISTS geographic_scope_updated_at ON geographic_scope;
DROP FUNCTION IF EXISTS hydro_set_updated_at();
DROP TABLE hydro_hypothesis_evidence;
DROP TABLE hydro_hypothesis;
DROP TABLE climate_context;
DROP TABLE reservoir_operation_event;
DROP TABLE reservoir;
DROP TABLE source_health;
DROP TABLE hydrological_observation;
DROP TABLE hydrological_station;
DROP TABLE geographic_scope;

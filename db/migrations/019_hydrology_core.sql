-- Phase 1P.1: global, evidence-first hydrology reference data.
-- These tables deliberately have no tenant_id.  Public observations are stored
-- once; tenant-specific exposure, assessment, alert and action records remain
-- in the existing tenant-scoped domain.

CREATE TABLE geographic_scope (
  id uuid PRIMARY KEY,
  scope_key text NOT NULL UNIQUE,
  name text NOT NULL,
  geometry geometry(Geometry, 4326),
  geometry_status text NOT NULL CHECK (geometry_status IN ('VERIFIED','UNKNOWN')),
  discovery_criteria text NOT NULL,
  source_reference text,
  classification text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE hydrological_station (
  id uuid PRIMARY KEY,
  provider text NOT NULL,
  provider_station_id text NOT NULL,
  name text NOT NULL,
  station_type text NOT NULL,
  river_name text,
  latitude numeric,
  longitude numeric,
  elevation numeric,
  municipality text,
  state text,
  basin text,
  subbasin text,
  active_status text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (provider, provider_station_id),
  CHECK ((latitude IS NULL AND longitude IS NULL) OR
         (latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180))
);

CREATE TABLE hydrological_observation (
  id uuid PRIMARY KEY,
  station_id uuid NOT NULL REFERENCES hydrological_station(id),
  provider text NOT NULL,
  variable text NOT NULL CHECK (variable IN ('RAINFALL','RIVER_STAGE','DISCHARGE')),
  observed_at timestamptz NOT NULL,
  received_at timestamptz NOT NULL,
  value numeric NOT NULL,
  unit text NOT NULL,
  quality_flag text NOT NULL,
  classification text NOT NULL,
  raw_reference text,
  source_fetched_at timestamptz NOT NULL,
  parser_version text,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (station_id, variable, observed_at, provider)
);

CREATE TABLE source_health (
  provider text PRIMARY KEY,
  status text NOT NULL CHECK (status IN ('AVAILABLE','DEGRADED','STALE','SOURCE_UNAVAILABLE')),
  last_attempt timestamptz,
  last_success timestamptz,
  last_observation timestamptz,
  latency_seconds numeric,
  failure_code text,
  failure_detail_sanitized text,
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (latency_seconds IS NULL OR latency_seconds >= 0)
);

CREATE TABLE reservoir (
  id uuid PRIMARY KEY,
  provider text NOT NULL,
  provider_reservoir_id text NOT NULL,
  name text NOT NULL,
  river_name text,
  geometry geometry(Geometry, 4326),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (provider, provider_reservoir_id)
);

CREATE TABLE reservoir_operation_event (
  id uuid PRIMARY KEY,
  reservoir_id uuid NOT NULL REFERENCES reservoir(id),
  provider text NOT NULL,
  event_type text NOT NULL CHECK (event_type IN (
    'GATE_OPENING','GATE_CLOSING','SPILL_INCREASE','SPILL_DECREASE',
    'LEVEL_NOTICE','DOWNSTREAM_FLOW_WARNING','OTHER'
  )),
  published_at timestamptz NOT NULL,
  effective_at timestamptz,
  numeric_value numeric,
  unit text,
  description_sanitized text NOT NULL,
  source_reference text NOT NULL,
  classification text NOT NULL,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (provider, source_reference, event_type)
);

CREATE TABLE climate_context (
  id uuid PRIMARY KEY,
  provider text NOT NULL,
  issued_on date NOT NULL,
  valid_window text,
  enso_state text NOT NULL CHECK (enso_state IN ('EL_NINO','LA_NINA','NEUTRAL','UNKNOWN')),
  probability numeric,
  strength_category text,
  source_reference text NOT NULL,
  classification text NOT NULL,
  source_fetched_at timestamptz NOT NULL,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (probability IS NULL OR probability BETWEEN 0 AND 100),
  UNIQUE (provider, issued_on, enso_state, source_reference)
);

CREATE TABLE hydro_hypothesis (
  id uuid PRIMARY KEY,
  hypothesis_key text NOT NULL UNIQUE,
  title text NOT NULL,
  geographic_scope_id uuid REFERENCES geographic_scope(id),
  start_at timestamptz,
  end_at timestamptz,
  status text NOT NULL CHECK (status IN (
    'SUPPORTED','PARTIALLY_SUPPORTED','INCONCLUSIVE','CONTRADICTED','UNKNOWN'
  )),
  confidence numeric,
  method text NOT NULL,
  limitations text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
  CHECK (end_at IS NULL OR start_at IS NULL OR end_at >= start_at)
);

-- Existing evidence is tenant-scoped by design.  This relation gives global
-- hydro facts the same traceability without forging a tenant ownership link.
CREATE TABLE hydro_hypothesis_evidence (
  id uuid PRIMARY KEY,
  hypothesis_id uuid NOT NULL REFERENCES hydro_hypothesis(id) ON DELETE CASCADE,
  observation_id uuid REFERENCES hydrological_observation(id),
  reservoir_operation_event_id uuid REFERENCES reservoir_operation_event(id),
  climate_context_id uuid REFERENCES climate_context(id),
  source_reference text,
  relationship text NOT NULL CHECK (relationship IN ('SUPPORTING','CONTRADICTING','UNKNOWN')),
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (
    (CASE WHEN observation_id IS NULL THEN 0 ELSE 1 END) +
    (CASE WHEN reservoir_operation_event_id IS NULL THEN 0 ELSE 1 END) +
    (CASE WHEN climate_context_id IS NULL THEN 0 ELSE 1 END) +
    (CASE WHEN source_reference IS NULL THEN 0 ELSE 1 END) = 1
  )
);

CREATE INDEX hydrological_observation_station_time_idx
  ON hydrological_observation (station_id, observed_at DESC);
CREATE INDEX reservoir_operation_event_reservoir_time_idx
  ON reservoir_operation_event (reservoir_id, published_at DESC);
CREATE INDEX climate_context_issued_idx ON climate_context (issued_on DESC);

CREATE FUNCTION hydro_set_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

CREATE TRIGGER geographic_scope_updated_at
  BEFORE UPDATE ON geographic_scope FOR EACH ROW EXECUTE FUNCTION hydro_set_updated_at();
CREATE TRIGGER hydrological_station_updated_at
  BEFORE UPDATE ON hydrological_station FOR EACH ROW EXECUTE FUNCTION hydro_set_updated_at();
CREATE TRIGGER reservoir_updated_at
  BEFORE UPDATE ON reservoir FOR EACH ROW EXECUTE FUNCTION hydro_set_updated_at();
CREATE TRIGGER hydro_hypothesis_updated_at
  BEFORE UPDATE ON hydro_hypothesis FOR EACH ROW EXECUTE FUNCTION hydro_set_updated_at();

-- No polygon is inserted: an official, verifiable spatial boundary is not yet
-- available.  Discovery is deliberately administrative and marked UNKNOWN.
INSERT INTO geographic_scope (
  id, scope_key, name, geometry, geometry_status, discovery_criteria,
  source_reference, classification
) VALUES (
  '00000000-0000-5000-8000-000000000019',
  'VALE_DO_RIBEIRA',
  'Vale do Ribeira',
  NULL,
  'UNKNOWN',
  'Administrative discovery only until an official spatial boundary is verified',
  NULL,
  'UNKNOWN'
)
ON CONFLICT (scope_key) DO NOTHING;

-- The reference tables are global, but access still runs through the private
-- application role.  Tenant-specific data remains protected by tenant RLS.
DO $$
DECLARE
  item record;
BEGIN
  FOR item IN SELECT * FROM (VALUES
    ('geographic_scope', 'geographic_scope_global_access'),
    ('hydrological_station', 'hydrological_station_global_access'),
    ('hydrological_observation', 'hydrological_observation_global_access'),
    ('source_health', 'source_health_global_access'),
    ('reservoir', 'reservoir_global_access'),
    ('reservoir_operation_event', 'reservoir_operation_event_global_access'),
    ('climate_context', 'climate_context_global_access'),
    ('hydro_hypothesis', 'hydro_hypothesis_global_access'),
    ('hydro_hypothesis_evidence', 'hydro_hypothesis_evidence_global_access')
  ) AS policy_items(table_name, policy_name)
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', item.table_name);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', item.table_name);
    EXECUTE format('CREATE POLICY %I ON %I FOR ALL TO ribeira_app USING (true) WITH CHECK (true)', item.policy_name, item.table_name);
  END LOOP;
END
$$;

GRANT SELECT, INSERT, UPDATE, DELETE ON
  geographic_scope, hydrological_station, hydrological_observation, source_health,
  reservoir, reservoir_operation_event, climate_context, hydro_hypothesis,
  hydro_hypothesis_evidence
TO ribeira_app;

-- Reusable Evidence First flood-event context and tenant-isolated exposure.
-- A municipal report is contextual evidence, never a property flood geometry.

CREATE TABLE flood_event_profile (
  event_id uuid PRIMARY KEY REFERENCES operational_event(id) ON DELETE CASCADE,
  evidence_status text NOT NULL CHECK (evidence_status IN ('UNKNOWN','INCONCLUSIVE','PARTIALLY_SUPPORTED','SUPPORTED')),
  classification text NOT NULL CHECK (classification = 'FACTUAL_EVIDENCE_ONLY'),
  limitations jsonb NOT NULL DEFAULT '[]'::jsonb,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE flood_event_hypothesis (
  id uuid PRIMARY KEY,
  event_id uuid NOT NULL REFERENCES operational_event(id) ON DELETE CASCADE,
  hypothesis_key text NOT NULL CHECK (hypothesis_key IN ('H1_LOCAL_RAINFALL','H2_UPSTREAM_RAINFALL','H3_RESERVOIR_OPERATION','H4_ENSO_CONTEXT')),
  title text NOT NULL,
  status text NOT NULL CHECK (status IN ('SUPPORTED','PARTIALLY_SUPPORTED','INCONCLUSIVE','CONTRADICTED','UNKNOWN')),
  method text NOT NULL,
  limitations jsonb NOT NULL DEFAULT '[]'::jsonb,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(event_id,hypothesis_key)
);

CREATE TABLE flood_event_hypothesis_evidence (
  id uuid PRIMARY KEY,
  hypothesis_id uuid NOT NULL REFERENCES flood_event_hypothesis(id) ON DELETE CASCADE,
  source_table text NOT NULL,
  source_record_id uuid,
  source_reference text,
  relationship text NOT NULL CHECK (relationship IN ('SUPPORTING','CONTRADICTING','CONTEXT_ONLY','UNKNOWN')),
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK ((source_record_id IS NULL) <> (source_reference IS NULL))
);

CREATE TABLE flood_event_exposure_zone (
  id uuid PRIMARY KEY,
  event_id uuid NOT NULL REFERENCES operational_event(id) ON DELETE CASCADE,
  zone_type text NOT NULL CHECK (zone_type IN ('FLOOD_EXTENT','OPEN_WATER_SIGNAL','EVACUATION_AREA','OTHER')),
  geometry geometry(Geometry,4326),
  geometry_status text NOT NULL CHECK (geometry_status IN ('VERIFIED','UNKNOWN')),
  classification text NOT NULL CHECK (classification IN ('OBSERVED','OFFICIAL_SOURCE','CALCULATED','DERIVED','SIMULATED','UNKNOWN')),
  method text NOT NULL,
  source_reference text,
  limitations jsonb NOT NULL DEFAULT '[]'::jsonb,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK ((geometry_status = 'VERIFIED' AND geometry IS NOT NULL) OR (geometry_status = 'UNKNOWN' AND geometry IS NULL))
);
CREATE INDEX flood_event_exposure_zone_event_idx ON flood_event_exposure_zone(event_id,zone_type);
CREATE INDEX flood_event_exposure_zone_geometry_gix ON flood_event_exposure_zone USING gist(geometry);

CREATE TABLE flood_event_municipality_context (
  id uuid PRIMARY KEY,
  event_id uuid NOT NULL REFERENCES operational_event(id) ON DELETE CASCADE,
  municipality_id uuid NOT NULL REFERENCES municipality_reference(id),
  report_status text NOT NULL CHECK (report_status IN ('AFFECTED_REPORTED','NO_REPORT','UNKNOWN')),
  source_reference text NOT NULL,
  observed_at timestamptz,
  classification text NOT NULL CHECK (classification IN ('OFFICIAL_SOURCE','OBSERVED','MANUAL_CONFIRMED','UNKNOWN')),
  limitations jsonb NOT NULL DEFAULT '[]'::jsonb,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(event_id,municipality_id,source_reference)
);

CREATE TABLE tenant_flood_exposure_assessment (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  event_id uuid NOT NULL REFERENCES operational_event(id),
  exposure_zone_id uuid REFERENCES flood_event_exposure_zone(id),
  subject_type text NOT NULL CHECK (subject_type IN ('PROPERTY','ASSET')),
  property_id uuid REFERENCES property(id),
  asset_id uuid REFERENCES asset(id),
  status text NOT NULL CHECK (status IN ('EXPOSED','NOT_EXPOSED','UNKNOWN')),
  classification text NOT NULL CHECK (classification IN ('CALCULATED','UNKNOWN')),
  method text NOT NULL,
  intersection_km2 numeric,
  limitations jsonb NOT NULL DEFAULT '[]'::jsonb,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  assessed_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK ((subject_type='PROPERTY' AND property_id IS NOT NULL AND asset_id IS NULL) OR (subject_type='ASSET' AND asset_id IS NOT NULL AND property_id IS NULL)),
  CHECK ((status='UNKNOWN' AND classification='UNKNOWN' AND intersection_km2 IS NULL) OR (status IN ('EXPOSED','NOT_EXPOSED') AND classification='CALCULATED' AND intersection_km2 IS NOT NULL AND intersection_km2 >= 0))
);
CREATE INDEX tenant_flood_exposure_assessment_lookup_idx ON tenant_flood_exposure_assessment(tenant_id,event_id,subject_type,assessed_at DESC);

CREATE FUNCTION flood_exposure_subject_tenant_check()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.subject_type = 'PROPERTY' AND NOT EXISTS (
    SELECT 1 FROM property WHERE id=NEW.property_id AND tenant_id=NEW.tenant_id
  ) THEN
    RAISE EXCEPTION 'flood exposure property must belong to tenant';
  END IF;
  IF NEW.subject_type = 'ASSET' AND NOT EXISTS (
    SELECT 1 FROM asset WHERE id=NEW.asset_id AND tenant_id=NEW.tenant_id
  ) THEN
    RAISE EXCEPTION 'flood exposure asset must belong to tenant';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER tenant_flood_exposure_assessment_subject_tenant_check
  BEFORE INSERT OR UPDATE ON tenant_flood_exposure_assessment
  FOR EACH ROW EXECUTE FUNCTION flood_exposure_subject_tenant_check();

CREATE TRIGGER flood_event_profile_updated_at BEFORE UPDATE ON flood_event_profile
  FOR EACH ROW EXECUTE FUNCTION hydro_set_updated_at();
CREATE TRIGGER flood_event_hypothesis_updated_at BEFORE UPDATE ON flood_event_hypothesis
  FOR EACH ROW EXECUTE FUNCTION hydro_set_updated_at();
CREATE TRIGGER flood_event_exposure_zone_updated_at BEFORE UPDATE ON flood_event_exposure_zone
  FOR EACH ROW EXECUTE FUNCTION hydro_set_updated_at();

-- Preserve the September incident as factual context with separate, non-causal
-- hypotheses. No exposure zone or tenant assessment is seeded here.
INSERT INTO flood_event_profile(event_id,evidence_status,classification,limitations,provenance)
SELECT id,'INCONCLUSIVE','FACTUAL_EVIDENCE_ONLY',
  '["Flood extent and property/asset exposure remain unknown without a verified exposure zone"]'::jsonb,
  '{"event_key":"VALE_RIBEIRA_FLOOD_2026_09","method":"evidence_first_factual_event_profile_v1"}'::jsonb
FROM operational_event WHERE event_key='VALE_RIBEIRA_FLOOD_2026_09'
ON CONFLICT (event_id) DO NOTHING;
INSERT INTO flood_event_hypothesis(id,event_id,hypothesis_key,title,status,method,limitations,provenance)
SELECT md5(event.id::text || item.key)::uuid, event.id, item.key, item.title, item.status,
  'separate evidence-first causal hypothesis; temporal association is not causation',
  item.limitations::jsonb, '{"event_key":"VALE_RIBEIRA_FLOOD_2026_09"}'::jsonb
FROM operational_event event
CROSS JOIN (VALUES
  ('H1_LOCAL_RAINFALL','Local rainfall contribution','INCONCLUSIVE','["Requires location and time-specific rainfall-to-exposure evidence"]'),
  ('H2_UPSTREAM_RAINFALL','Upstream rainfall contribution','UNKNOWN','["Verified upstream rainfall and river sequence are unavailable"]'),
  ('H3_RESERVOIR_OPERATION','Reservoir/Capivari operation contribution','INCONCLUSIVE','["Operational timing alone does not establish contribution"]'),
  ('H4_ENSO_CONTEXT','ENSO/El Niño broader climate context','INCONCLUSIVE','["Climate context is not an event-causation conclusion"]')
) AS item(key,title,status,limitations)
WHERE event.event_key='VALE_RIBEIRA_FLOOD_2026_09'
ON CONFLICT (event_id,hypothesis_key) DO NOTHING;

DO $$
DECLARE item record;
BEGIN
  FOR item IN SELECT * FROM (VALUES
    ('flood_event_profile','flood_event_profile_global_access'),
    ('flood_event_hypothesis','flood_event_hypothesis_global_access'),
    ('flood_event_hypothesis_evidence','flood_event_hypothesis_evidence_global_access'),
    ('flood_event_exposure_zone','flood_event_exposure_zone_global_access')
  ) AS valueset(table_name,policy_name)
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',item.table_name);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',item.table_name);
    EXECUTE format('CREATE POLICY %I ON %I FOR ALL TO ribeira_app USING (true) WITH CHECK (true)',item.policy_name,item.table_name);
  END LOOP;
END $$;
ALTER TABLE flood_event_municipality_context ENABLE ROW LEVEL SECURITY;
ALTER TABLE flood_event_municipality_context FORCE ROW LEVEL SECURITY;
CREATE POLICY flood_event_municipality_context_global_access ON flood_event_municipality_context
  FOR ALL TO ribeira_app USING (true) WITH CHECK (true);
ALTER TABLE tenant_flood_exposure_assessment ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_flood_exposure_assessment FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_flood_exposure_assessment_tenant_isolation ON tenant_flood_exposure_assessment
  FOR ALL TO ribeira_app
  USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
  WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);

GRANT SELECT,INSERT,UPDATE,DELETE ON flood_event_profile,flood_event_hypothesis,
  flood_event_hypothesis_evidence,flood_event_exposure_zone,
  flood_event_municipality_context,tenant_flood_exposure_assessment TO ribeira_app;

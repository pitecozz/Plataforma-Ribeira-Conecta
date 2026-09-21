-- Phase 1P.3: global spatial scope and municipal production baseline.
ALTER TABLE geographic_scope
  ADD COLUMN scope_type text NOT NULL DEFAULT 'OPERATIONAL_REGION'
    CHECK (scope_type IN ('ADMINISTRATIVE_REGION','OPERATIONAL_REGION','HYDROLOGICAL_BASIN')),
  ADD COLUMN source text,
  ADD COLUMN source_version text,
  ADD COLUMN valid_from date,
  ADD COLUMN metadata jsonb NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE municipality_reference (
  id uuid PRIMARY KEY,
  ibge_code text NOT NULL,
  name text NOT NULL,
  uf text NOT NULL CHECK (uf IN ('SP','PR')),
  source_year integer NOT NULL CHECK (source_year >= 2025),
  geometry geometry(MultiPolygon, 4674) NOT NULL,
  source_reference text NOT NULL,
  source_sha256 text NOT NULL CHECK (length(source_sha256) = 64),
  classification text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (ibge_code, source_year)
);

CREATE TABLE spatial_scope_definition (
  id uuid PRIMARY KEY,
  geographic_scope_id uuid NOT NULL REFERENCES geographic_scope(id),
  source text NOT NULL,
  source_version text,
  definition_status text NOT NULL CHECK (definition_status IN ('VERIFIED','CONFLICTING_SCOPE_DEFINITION','UNKNOWN')),
  definition_reference text NOT NULL,
  municipality_criteria jsonb NOT NULL DEFAULT '[]'::jsonb,
  classification text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE spatial_scope_municipality (
  geographic_scope_id uuid NOT NULL REFERENCES geographic_scope(id),
  municipality_id uuid NOT NULL REFERENCES municipality_reference(id),
  definition_id uuid NOT NULL REFERENCES spatial_scope_definition(id),
  classification text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (geographic_scope_id, municipality_id, definition_id)
);

CREATE TABLE banana_municipal_baseline (
  id uuid PRIMARY KEY,
  municipality_id uuid NOT NULL REFERENCES municipality_reference(id),
  reference_year integer NOT NULL,
  crop text NOT NULL CHECK (crop = 'BANANA'),
  area_planted_or_destined numeric,
  area_harvested numeric,
  production_quantity numeric,
  average_yield numeric,
  production_value numeric,
  units jsonb NOT NULL,
  source_reference text NOT NULL,
  classification text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (municipality_id, reference_year, crop)
);

-- Official textual definitions are kept separate. No municipal geometry is
-- fabricated until the 2025 IBGE import supplies a verifiable polygon.
INSERT INTO geographic_scope(id,scope_key,name,geometry_status,discovery_criteria,classification,scope_type,source,source_version,metadata)
VALUES
('00000000-0000-5000-8000-000000000201','VALE_DO_RIBEIRA_SP_SEMIL','Vale do Ribeira paulista','UNKNOWN','Official SP regional definition; geometry derived only from IBGE 2025 municipalities','OFFICIAL_SOURCE','ADMINISTRATIVE_REGION','SEMIL','public regional definition',jsonb_build_object('geometry_pending','IBGE_MUNICIPAL_2025')),
('00000000-0000-5000-8000-000000000202','VALE_DO_RIBEIRA_INTERSTATE_IPARDES','Vale do Ribeira interestadual','UNKNOWN','Official operational regional publication; no basin equivalence asserted','OFFICIAL_SOURCE','OPERATIONAL_REGION','IPARDES','2003',jsonb_build_object('geometry_pending','OFFICIAL_CURRENT_BOUNDARY')),
('00000000-0000-5000-8000-000000000203','RIBEIRA_DE_IGUAPE_BASIN','Bacia hidrográfica Ribeira de Iguape','UNKNOWN','Hydrological basin requires an official basin polygon; no administrative substitution','UNKNOWN','HYDROLOGICAL_BASIN','PENDING_OFFICIAL_BASIN_DATASET',NULL,'{}'::jsonb)
ON CONFLICT (scope_key) DO NOTHING;

INSERT INTO spatial_scope_definition(id,geographic_scope_id,source,source_version,definition_status,definition_reference,classification)
VALUES
('00000000-0000-5000-8000-000000000211','00000000-0000-5000-8000-000000000201','SEMIL','public regional definition','VERIFIED','https://semil.sp.gov.br/sma/gerco/','OFFICIAL_SOURCE'),
('00000000-0000-5000-8000-000000000212','00000000-0000-5000-8000-000000000202','IPARDES','2003','VERIFIED','https://www.ipardes.pr.gov.br/sites/ipardes/arquivos_restritos/files/documento/2020-03/RP_vale_ribeira_2003_1.pdf','OFFICIAL_SOURCE'),
('00000000-0000-5000-8000-000000000213','00000000-0000-5000-8000-000000000203','SP_AGUAS','public directorate description','CONFLICTING_SCOPE_DEFINITION','https://www.spaguas.sp.gov.br/site/brb/','OFFICIAL_SOURCE')
ON CONFLICT (id) DO NOTHING;

DO $$
DECLARE item record;
BEGIN
  FOR item IN SELECT * FROM (VALUES
    ('municipality_reference','municipality_reference_global_access'),
    ('spatial_scope_definition','spatial_scope_definition_global_access'),
    ('spatial_scope_municipality','spatial_scope_municipality_global_access'),
    ('banana_municipal_baseline','banana_municipal_baseline_global_access')
  ) AS valueset(table_name,policy_name)
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',item.table_name);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',item.table_name);
    EXECUTE format('CREATE POLICY %I ON %I FOR ALL TO ribeira_app USING (true) WITH CHECK (true)',item.policy_name,item.table_name);
  END LOOP;
END $$;
GRANT SELECT,INSERT,UPDATE,DELETE ON municipality_reference,spatial_scope_definition,spatial_scope_municipality,banana_municipal_baseline TO ribeira_app;

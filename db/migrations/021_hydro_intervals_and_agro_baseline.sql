-- Phase 1P.3G: preserve WIS2 report semantics and official PAM evidence.
-- Migration 020 is intentionally not modified.

ALTER TABLE hydrological_observation
  ADD COLUMN period_start timestamptz,
  ADD COLUMN period_end timestamptz,
  ADD COLUMN provider_record_id text,
  ADD COLUMN delivery_channel text,
  ADD COLUMN raw_unit text,
  ADD COLUMN normalized_value numeric,
  ADD COLUMN normalized_unit text,
  ADD COLUMN provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD CONSTRAINT hydrological_observation_period_complete
    CHECK (
      (period_start IS NULL AND period_end IS NULL)
      OR (period_start IS NOT NULL AND period_end IS NOT NULL AND period_start <= period_end)
    );

CREATE UNIQUE INDEX hydrological_observation_provider_record_identity
  ON hydrological_observation(provider, provider_record_id)
  WHERE provider_record_id IS NOT NULL;

ALTER TABLE banana_municipal_baseline
  ADD COLUMN classification_id text,
  ADD COLUMN classification_label text,
  ADD COLUMN category_id text,
  ADD COLUMN category_label text,
  ADD COLUMN raw_values jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN data_status text NOT NULL DEFAULT 'WITH_DATA'
    CHECK (data_status IN ('WITH_DATA','MISSING','PARTIAL'));

-- This is the already verified official SEMIL municipal definition.  The
-- geometry remains derived only from the official 2025 IBGE municipal mesh.
UPDATE spatial_scope_definition
   SET municipality_criteria = jsonb_build_array(
     'Apiaí','Barra do Chapéu','Barra do Turvo','Cajati','Eldorado',
     'Iporanga','Itaóca','Itapirapuã Paulista','Itariri','Jacupiranga',
     'Juquiá','Juquitiba','Miracatu','Pariquera-Açu','Pedro de Toledo',
     'Registro','Ribeira','São Lourenço da Serra','Sete Barras','Tapiraí'
   )
 WHERE id = '00000000-0000-5000-8000-000000000211'
   AND municipality_criteria = '[]'::jsonb;

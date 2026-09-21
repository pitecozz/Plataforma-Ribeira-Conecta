-- Trace the result of a non-automated action without overwriting its decision.
ALTER TABLE action
  ADD COLUMN completed_at timestamptz,
  ADD COLUMN completed_by text,
  ADD COLUMN outcome_detail text,
  ADD COLUMN outcome_classification text,
  ADD COLUMN outcome_evidence_ids jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE action ADD CONSTRAINT action_outcome_state_check CHECK (
  (status <> 'COMPLETED' AND completed_at IS NULL AND completed_by IS NULL AND outcome_detail IS NULL AND outcome_classification IS NULL AND outcome_evidence_ids = '[]'::jsonb)
  OR (status = 'COMPLETED' AND completed_at IS NOT NULL AND completed_by IS NOT NULL AND outcome_detail IS NOT NULL AND outcome_classification IS NOT NULL)
);
ALTER TABLE action ADD CONSTRAINT action_outcome_classification_check CHECK (
  outcome_classification IS NULL OR outcome_classification IN (
    'OBSERVED', 'OFFICIAL_SOURCE', 'MANUAL_CONFIRMED', 'CALCULATED', 'DERIVED',
    'INFERRED', 'PREDICTED', 'ASSUMPTION', 'SIMULATED', 'UNKNOWN', 'CONFLICTING'
  )
);

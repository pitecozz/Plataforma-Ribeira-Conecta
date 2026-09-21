DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM action WHERE completed_at IS NOT NULL) THEN
    RAISE EXCEPTION 'cannot rollback 029 after action outcomes have been stored';
  END IF;
END $$;
ALTER TABLE action DROP CONSTRAINT action_outcome_classification_check;
ALTER TABLE action DROP CONSTRAINT action_outcome_state_check;
ALTER TABLE action DROP COLUMN outcome_evidence_ids;
ALTER TABLE action DROP COLUMN outcome_classification;
ALTER TABLE action DROP COLUMN outcome_detail;
ALTER TABLE action DROP COLUMN completed_by;
ALTER TABLE action DROP COLUMN completed_at;

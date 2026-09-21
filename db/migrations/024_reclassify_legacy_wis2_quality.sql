-- A timer execution from the pre-023 collector can race a code deployment.
-- Reclassify only those legacy counters; raw observations remain untouched.
UPDATE hydro_ingestion_run
   SET observations_ignored = observations_ignored + invalid_observations,
       quality_reason_counts = quality_reason_counts || jsonb_build_object(
         'LEGACY_IGNORED_SCOPE_OR_MISSING_VALUE', invalid_observations
       ),
       invalid_observations = 0
 WHERE provider = 'INMET_WIS2'
   AND invalid_observations > 0;

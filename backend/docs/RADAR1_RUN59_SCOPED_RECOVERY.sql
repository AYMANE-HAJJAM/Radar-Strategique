-- Proposed recovery only. DO NOT EXECUTE without the user's explicit approval.
-- Completed Render replacement confirmed; Neon snapshot 2026-10-10 10:04 UTC.
-- Changes ONLY search_runs.id=59. No listing, result or review writes.
BEGIN;
SET LOCAL statement_timeout = '8s';
SET LOCAL lock_timeout = '2s';
SET LOCAL TIME ZONE 'UTC';

DO $recovery$
DECLARE
  affected integer;
BEGIN
  PERFORM id FROM search_runs WHERE id = 59 FOR UPDATE NOWAIT;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Run 59 missing; abort';
  END IF;
  IF EXISTS (SELECT 1 FROM pmmp_listing_index WHERE processing_run_id = 59)
     OR EXISTS (SELECT 1 FROM result_observations WHERE run_id = 59)
     OR (SELECT count(*) FROM pmmp_listing_index
         WHERE processing_state = 'PENDING_PROCESSING') <> 1808 THEN
    RAISE EXCEPTION 'Claims, observations or pending count changed; abort';
  END IF;

  UPDATE search_runs
  SET status = 'failed', current_stage = 'FAILED',
      finished_at = transaction_timestamp(),
      error_kind = 'abandoned_worker_confirmed',
      error_message = 'Completed Render replacement confirmed; scoped recovery of abandoned run 59.',
      stage_history = (COALESCE(stage_history::jsonb, '[]'::jsonb) ||
        jsonb_build_array(jsonb_build_object(
          'stage', 'FAILED', 'at', transaction_timestamp(),
          'reason', 'abandoned_worker_confirmed')))::json
  WHERE id = 59 AND radar_id = 1
    AND status = 'running' AND current_stage = 'COLLECTING'
    AND started_at = TIMESTAMPTZ '2026-10-09 16:51:39.570765+00'
    AND finished_at IS NULL
    AND candidates_count = 0 AND analyzed_count = 0 AND accepted_count = 0
    AND manual_review_count = 0 AND new_results_count = 0 AND updated_results_count = 0
    AND run_metadata->'collector_metrics'->>'pmmp_sync_pages' = '339'
    AND run_metadata->'collector_metrics'->>'pmmp_discovery_strategy' = 'complete_board_comparison'
    AND run_metadata->'collector_metrics'->>'pmmp_policy_version' = 'archeritage-r10';

  GET DIAGNOSTICS affected = ROW_COUNT;
  IF affected <> 1 THEN
    RAISE EXCEPTION 'Run 59 changed; abort';
  END IF;
END;
$recovery$;

SELECT id, radar_id, status, current_stage, finished_at, error_kind
FROM search_runs WHERE id = 59;
COMMIT;

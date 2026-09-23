-- FGF YouTube pipeline monitoring
-- Run in Supabase SQL editor when you want a compact operational view.

create or replace view public.fgf_youtube_pipeline_status as
select
  (select count(*) from public.video_database) as videos_persisted,
  (select count(*) from public.video_claim_candidates) as candidate_claims,
  (select count(*) from public.video_claim_candidates where status = 'candidate') as candidate_status_claims,
  (select count(*) from public.video_claim_candidates where evidence_tier = 3) as tier3_claims,
  (select count(*) from public.video_processing_runs) as processing_runs,
  (select count(*) from public.video_processing_runs where status = 'failed') as failed_processing_runs,
  (select max(completed_at) from public.video_processing_runs) as last_completed_processing_run;

-- =============================================
-- 003-add-alert-ai-assessment-column.sql
-- Add dedicated AI assessment column on alerts
-- for concise operator-facing reasoning text.
-- =============================================

BEGIN;

ALTER TABLE public.alerts
  ADD COLUMN IF NOT EXISTS ai_assessment text;

-- Backfill existing rows with current summary text where available.
UPDATE public.alerts
SET ai_assessment = COALESCE(ai_assessment, analysis_summary)
WHERE ai_assessment IS NULL
  AND analysis_summary IS NOT NULL;

COMMIT;

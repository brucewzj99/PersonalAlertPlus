-- =============================================
-- 006-add-alert-operator-remarks-column.sql
-- Add operator remarks field for case closure notes.
-- =============================================

BEGIN;

ALTER TABLE public.alerts
  ADD COLUMN IF NOT EXISTS operator_remarks text;

COMMIT;

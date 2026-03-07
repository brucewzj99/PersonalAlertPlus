-- =============================================
-- 002-remove-legacy-alert-action-columns.sql
-- Drop legacy operator action booleans from alerts
-- after app code has moved to public.operator_actions.
-- =============================================

BEGIN;

DROP TRIGGER IF EXISTS trg_alerts_log_legacy_operator_actions ON public.alerts;
DROP FUNCTION IF EXISTS public.log_legacy_alert_operator_actions();

ALTER TABLE public.alerts
  DROP COLUMN IF EXISTS ambulance_dispatched,
  DROP COLUMN IF EXISTS family_called,
  DROP COLUMN IF EXISTS is_attended;

COMMIT;

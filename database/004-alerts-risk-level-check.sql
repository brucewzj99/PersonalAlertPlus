-- =============================================
-- Alerts table check constraints
-- Ensures risk_level and status accept the values the app writes.
-- Run this in Supabase SQL Editor if writes fail with constraint violations.
-- Backend must use service_role key (SUPABASE_SECRET_KEY) to bypass RLS.
-- =============================================

-- risk_level: app sends UPPERCASE URGENT/NON_URGENT/UNCERTAIN/FALSE_ALARM
ALTER TABLE public.alerts
DROP CONSTRAINT IF EXISTS alerts_risk_level_check;

ALTER TABLE public.alerts
ADD CONSTRAINT alerts_risk_level_check
CHECK (
    risk_level IS NULL OR risk_level IN ('URGENT', 'NON_URGENT', 'UNCERTAIN', 'FALSE_ALARM')
);

-- status values used by brain/operator flows
ALTER TABLE public.alerts
DROP CONSTRAINT IF EXISTS alerts_status_check;

ALTER TABLE public.alerts
ADD CONSTRAINT alerts_status_check
CHECK (
    status IS NULL OR status IN ('pending', 'pending_confirmation', 'escalated', 'closed')
);

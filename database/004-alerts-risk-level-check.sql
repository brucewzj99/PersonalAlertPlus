-- =============================================
-- Alerts table check constraints
-- Ensures risk_level and status accept the values the app writes.
-- Run this in Supabase SQL Editor if writes fail with constraint violations.
-- Backend must use service_role key (SUPABASE_SECRET_KEY) to bypass RLS.
-- =============================================

-- risk_level: app sends lowercase high | medium | low
ALTER TABLE public.alerts
DROP CONSTRAINT IF EXISTS alerts_risk_level_check;

ALTER TABLE public.alerts
ADD CONSTRAINT alerts_risk_level_check
CHECK (risk_level IS NULL OR risk_level IN ('high', 'medium', 'low'));

-- status: app sends pending | escalated (and operators may set closed)
ALTER TABLE public.alerts
DROP CONSTRAINT IF EXISTS alerts_status_check;

ALTER TABLE public.alerts
ADD CONSTRAINT alerts_status_check
CHECK (status IS NULL OR status IN ('pending', 'escalated', 'closed'));

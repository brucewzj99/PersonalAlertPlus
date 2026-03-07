-- =============================================
-- Alert Risk Model Migration (v004)
-- =============================================

BEGIN;

-- 1) Emergency contact preference for UNCERTAIN notifications
ALTER TABLE public.emergency_contacts
ADD COLUMN IF NOT EXISTS notify_on_uncertain boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN public.emergency_contacts.notify_on_uncertain IS
'When true, this contact can be notified for UNCERTAIN alerts.';

-- 2) Backfill and normalize risk levels
UPDATE public.alerts
SET risk_level = CASE UPPER(COALESCE(risk_level, ''))
    WHEN 'HIGH' THEN 'URGENT'
    WHEN 'MEDIUM' THEN 'UNCERTAIN'
    WHEN 'LOW' THEN 'FALSE_ALARM'
    WHEN 'URGENT' THEN 'URGENT'
    WHEN 'NON_URGENT' THEN 'NON_URGENT'
    WHEN 'UNCERTAIN' THEN 'UNCERTAIN'
    WHEN 'FALSE_ALARM' THEN 'FALSE_ALARM'
    ELSE risk_level
END;

-- 3) Align status/operator flags to new model where possible
UPDATE public.alerts
SET requires_operator = true,
    status = 'escalated'
WHERE risk_level IN ('URGENT', 'NON_URGENT');

UPDATE public.alerts
SET requires_operator = false,
    status = CASE WHEN status = 'escalated' THEN 'pending_confirmation' ELSE status END
WHERE risk_level = 'UNCERTAIN';

UPDATE public.alerts
SET requires_operator = false,
    status = CASE WHEN status IN ('pending', 'pending_confirmation') THEN 'closed' ELSE status END
WHERE risk_level = 'FALSE_ALARM';

-- 4) Enforce valid risk categories going forward
ALTER TABLE public.alerts DROP CONSTRAINT IF EXISTS alerts_risk_level_check;

ALTER TABLE public.alerts
ADD CONSTRAINT alerts_risk_level_check
CHECK (
    risk_level IS NULL OR risk_level IN ('URGENT', 'NON_URGENT', 'UNCERTAIN', 'FALSE_ALARM')
);

COMMENT ON COLUMN public.alerts.risk_level IS
'URGENT | NON_URGENT | UNCERTAIN | FALSE_ALARM';

COMMIT;

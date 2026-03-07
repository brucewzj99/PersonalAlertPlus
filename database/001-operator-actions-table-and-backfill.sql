-- =============================================
-- 001-operator-actions-table-and-backfill.sql
-- Add a generic operator_actions table and backfill
-- existing action booleans from public.alerts.
--
-- NOTE:
-- - This migration keeps legacy alert columns intact.
-- - It also adds a compatibility trigger so existing
--   dashboard/backend writes continue to be captured
--   in operator_actions until app code is migrated.
-- =============================================

BEGIN;

-- --------------------------------------------------
-- operator_actions (generic operator action log)
-- --------------------------------------------------
CREATE TABLE IF NOT EXISTS public.operator_actions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  case_id uuid NOT NULL REFERENCES public.alerts(id) ON DELETE CASCADE,
  operator text NOT NULL DEFAULT 'Operator 1',
  actions_taken text NOT NULL,
  action_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  action_time timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_operator_actions_case_id
  ON public.operator_actions (case_id);
CREATE INDEX IF NOT EXISTS idx_operator_actions_case_time
  ON public.operator_actions (case_id, action_time DESC);
CREATE INDEX IF NOT EXISTS idx_operator_actions_operator
  ON public.operator_actions (operator);
CREATE INDEX IF NOT EXISTS idx_operator_actions_action
  ON public.operator_actions (actions_taken);

-- --------------------------------------------------
-- Backfill legacy boolean action columns from alerts
-- --------------------------------------------------
INSERT INTO public.operator_actions (
  case_id,
  operator,
  actions_taken,
  action_payload,
  action_time
)
SELECT
  a.id,
  'System Backfill',
  'dispatch_ambulance',
  jsonb_build_object(
    'source', 'alerts_boolean_backfill_v1',
    'legacy_column', 'ambulance_dispatched',
    'legacy_value', true
  ),
  COALESCE(a.created_at, now())
FROM public.alerts a
WHERE COALESCE(a.ambulance_dispatched, false) = true
  AND NOT EXISTS (
    SELECT 1
    FROM public.operator_actions oa
    WHERE oa.case_id = a.id
      AND oa.actions_taken = 'dispatch_ambulance'
      AND oa.action_payload ->> 'source' = 'alerts_boolean_backfill_v1'
  );

INSERT INTO public.operator_actions (
  case_id,
  operator,
  actions_taken,
  action_payload,
  action_time
)
SELECT
  a.id,
  'System Backfill',
  'call_family',
  jsonb_build_object(
    'source', 'alerts_boolean_backfill_v1',
    'legacy_column', 'family_called',
    'legacy_value', true
  ),
  COALESCE(a.created_at, now())
FROM public.alerts a
WHERE COALESCE(a.family_called, false) = true
  AND NOT EXISTS (
    SELECT 1
    FROM public.operator_actions oa
    WHERE oa.case_id = a.id
      AND oa.actions_taken = 'call_family'
      AND oa.action_payload ->> 'source' = 'alerts_boolean_backfill_v1'
  );

INSERT INTO public.operator_actions (
  case_id,
  operator,
  actions_taken,
  action_payload,
  action_time
)
SELECT
  a.id,
  'System Backfill',
  'mark_attended',
  jsonb_build_object(
    'source', 'alerts_boolean_backfill_v1',
    'legacy_column', 'is_attended',
    'legacy_value', true
  ),
  COALESCE(a.created_at, now())
FROM public.alerts a
WHERE COALESCE(a.is_attended, false) = true
  AND NOT EXISTS (
    SELECT 1
    FROM public.operator_actions oa
    WHERE oa.case_id = a.id
      AND oa.actions_taken = 'mark_attended'
      AND oa.action_payload ->> 'source' = 'alerts_boolean_backfill_v1'
  );

-- --------------------------------------------------
-- Compatibility trigger: keep logging action booleans
-- while legacy columns are still used by the app.
-- --------------------------------------------------
CREATE OR REPLACE FUNCTION public.log_legacy_alert_operator_actions()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    IF COALESCE(NEW.ambulance_dispatched, false) THEN
      INSERT INTO public.operator_actions (case_id, operator, actions_taken, action_payload)
      VALUES (
        NEW.id,
        COALESCE(NULLIF(NEW.resolved_by, ''), 'Operator 1'),
        'dispatch_ambulance',
        jsonb_build_object('source', 'legacy_alerts_trigger', 'op', 'insert')
      );
    END IF;

    IF COALESCE(NEW.family_called, false) THEN
      INSERT INTO public.operator_actions (case_id, operator, actions_taken, action_payload)
      VALUES (
        NEW.id,
        COALESCE(NULLIF(NEW.resolved_by, ''), 'Operator 1'),
        'call_family',
        jsonb_build_object('source', 'legacy_alerts_trigger', 'op', 'insert')
      );
    END IF;

    IF COALESCE(NEW.is_attended, false) THEN
      INSERT INTO public.operator_actions (case_id, operator, actions_taken, action_payload)
      VALUES (
        NEW.id,
        COALESCE(NULLIF(NEW.resolved_by, ''), 'Operator 1'),
        'mark_attended',
        jsonb_build_object('source', 'legacy_alerts_trigger', 'op', 'insert')
      );
    END IF;
  ELSIF TG_OP = 'UPDATE' THEN
    IF COALESCE(OLD.ambulance_dispatched, false) = false
       AND COALESCE(NEW.ambulance_dispatched, false) = true THEN
      INSERT INTO public.operator_actions (case_id, operator, actions_taken, action_payload)
      VALUES (
        NEW.id,
        COALESCE(NULLIF(NEW.resolved_by, ''), 'Operator 1'),
        'dispatch_ambulance',
        jsonb_build_object('source', 'legacy_alerts_trigger', 'op', 'update')
      );
    END IF;

    IF COALESCE(OLD.family_called, false) = false
       AND COALESCE(NEW.family_called, false) = true THEN
      INSERT INTO public.operator_actions (case_id, operator, actions_taken, action_payload)
      VALUES (
        NEW.id,
        COALESCE(NULLIF(NEW.resolved_by, ''), 'Operator 1'),
        'call_family',
        jsonb_build_object('source', 'legacy_alerts_trigger', 'op', 'update')
      );
    END IF;

    IF COALESCE(OLD.is_attended, false) = false
       AND COALESCE(NEW.is_attended, false) = true THEN
      INSERT INTO public.operator_actions (case_id, operator, actions_taken, action_payload)
      VALUES (
        NEW.id,
        COALESCE(NULLIF(NEW.resolved_by, ''), 'Operator 1'),
        'mark_attended',
        jsonb_build_object('source', 'legacy_alerts_trigger', 'op', 'update')
      );
    END IF;
  END IF;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_alerts_log_legacy_operator_actions ON public.alerts;
CREATE TRIGGER trg_alerts_log_legacy_operator_actions
AFTER INSERT OR UPDATE ON public.alerts
FOR EACH ROW
EXECUTE FUNCTION public.log_legacy_alert_operator_actions();

-- --------------------------------------------------
-- RLS + policies
-- --------------------------------------------------
ALTER TABLE public.operator_actions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Service role full access operator_actions" ON public.operator_actions;
CREATE POLICY "Service role full access operator_actions"
ON public.operator_actions FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Authenticated read operator_actions" ON public.operator_actions;
CREATE POLICY "Authenticated read operator_actions"
ON public.operator_actions FOR SELECT TO authenticated USING (true);

COMMIT;

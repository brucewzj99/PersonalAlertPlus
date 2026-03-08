-- =============================================
-- 004-operator-action-recommendations-table.sql
-- Store AI-generated operator response
-- recommendations and supporting context.
-- =============================================

BEGIN;

CREATE TABLE IF NOT EXISTS public.operator_action_recommendations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  case_id uuid NOT NULL REFERENCES public.alerts(id) ON DELETE CASCADE,
  model text,
  available_choices jsonb NOT NULL DEFAULT '[]'::jsonb,
  recommended_actions jsonb NOT NULL DEFAULT '[]'::jsonb,
  recommended_labels jsonb NOT NULL DEFAULT '[]'::jsonb,
  rationale text,
  confidence numeric,
  context_alert_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  raw_response jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_operator_action_reco_case_id
  ON public.operator_action_recommendations (case_id);

CREATE INDEX IF NOT EXISTS idx_operator_action_reco_created_at
  ON public.operator_action_recommendations (created_at DESC);

ALTER TABLE public.operator_action_recommendations ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Service role full access operator_action_recommendations" ON public.operator_action_recommendations;
CREATE POLICY "Service role full access operator_action_recommendations"
ON public.operator_action_recommendations FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Authenticated read operator_action_recommendations" ON public.operator_action_recommendations;
CREATE POLICY "Authenticated read operator_action_recommendations"
ON public.operator_action_recommendations FOR SELECT TO authenticated USING (true);

COMMIT;

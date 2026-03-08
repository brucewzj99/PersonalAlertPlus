-- =============================================
-- 000-master.sql
-- Fresh baseline schema for PersonalAlertPlus
-- Use this for clean environment bootstrap.
-- =============================================

BEGIN;

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- --------------------------------------------------
-- Utility: generic updated_at trigger
-- --------------------------------------------------
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

-- --------------------------------------------------
-- seniors
-- --------------------------------------------------
CREATE TABLE IF NOT EXISTS public.seniors (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  full_name text NOT NULL,
  phone_number text NOT NULL UNIQUE,
  telegram_user_id text,
  address text NOT NULL,
  birth_year int,
  birth_month int,
  birth_day int,
  preferred_language text,
  medical_notes text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_seniors_telegram_user_id
  ON public.seniors (telegram_user_id)
  WHERE telegram_user_id IS NOT NULL;

-- --------------------------------------------------
-- emergency_contacts
-- --------------------------------------------------
CREATE TABLE IF NOT EXISTS public.emergency_contacts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  senior_id uuid NOT NULL REFERENCES public.seniors(id) ON DELETE CASCADE,
  name text NOT NULL,
  relationship text,
  phone_number text,
  telegram_user_id text,
  priority_order int NOT NULL DEFAULT 1,
  notify_on_uncertain boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_emergency_contacts_senior_id
  ON public.emergency_contacts (senior_id);
CREATE INDEX IF NOT EXISTS idx_emergency_contacts_priority
  ON public.emergency_contacts (senior_id, priority_order);

-- --------------------------------------------------
-- alerts
-- --------------------------------------------------
CREATE TABLE IF NOT EXISTS public.alerts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  senior_id uuid NOT NULL REFERENCES public.seniors(id) ON DELETE CASCADE,
  channel text NOT NULL DEFAULT 'telegram',
  audio_url text,
  transcription text,
  language_detected text,
  translated_text text,
  risk_level text,
  risk_score numeric,
  status text NOT NULL DEFAULT 'pending',
  requires_operator boolean NOT NULL DEFAULT false,
  resolved_by text,
  processing_status text NOT NULL DEFAULT 'pending',
  processing_error text,
  analysis_summary text,
  keywords jsonb,
  senior_response text,
  operator_remarks text,
  ambulance_dispatched boolean NOT NULL DEFAULT false,
  family_called boolean NOT NULL DEFAULT false,
  is_resolved boolean NOT NULL DEFAULT false,
  is_attended boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.alerts DROP CONSTRAINT IF EXISTS alerts_risk_level_check;
ALTER TABLE public.alerts
  ADD CONSTRAINT alerts_risk_level_check
  CHECK (
    risk_level IS NULL OR risk_level IN ('URGENT', 'NON_URGENT', 'UNCERTAIN', 'FALSE_ALARM')
  );

ALTER TABLE public.alerts DROP CONSTRAINT IF EXISTS alerts_status_check;
ALTER TABLE public.alerts
  ADD CONSTRAINT alerts_status_check
  CHECK (
    status IS NULL OR status IN ('pending', 'pending_confirmation', 'escalated', 'closed')
  );

CREATE INDEX IF NOT EXISTS idx_alerts_created_at
  ON public.alerts (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_senior_id
  ON public.alerts (senior_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_risk_level
  ON public.alerts (risk_level, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_status
  ON public.alerts (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_processing_status
  ON public.alerts (processing_status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_is_resolved
  ON public.alerts (is_resolved);
CREATE INDEX IF NOT EXISTS idx_alerts_is_attended
  ON public.alerts (is_attended);

-- --------------------------------------------------
-- ai_actions
-- --------------------------------------------------
CREATE TABLE IF NOT EXISTS public.ai_actions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  alert_id uuid NOT NULL REFERENCES public.alerts(id) ON DELETE CASCADE,
  action_type text NOT NULL,
  action_status text NOT NULL DEFAULT 'pending',
  details jsonb,
  provider text,
  attempt_count int NOT NULL DEFAULT 1,
  external_ref text,
  error_message text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ai_actions_alert_id
  ON public.ai_actions (alert_id);
CREATE INDEX IF NOT EXISTS idx_ai_actions_created_at
  ON public.ai_actions (created_at DESC);

-- --------------------------------------------------
-- few_shot_examples
-- --------------------------------------------------
CREATE TABLE IF NOT EXISTS public.few_shot_examples (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  transcript text NOT NULL,
  risk_level text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.few_shot_examples DROP CONSTRAINT IF EXISTS few_shot_examples_risk_level_check;
ALTER TABLE public.few_shot_examples
  ADD CONSTRAINT few_shot_examples_risk_level_check
  CHECK (risk_level IN ('URGENT', 'NON_URGENT', 'UNCERTAIN', 'FALSE_ALARM'));

CREATE INDEX IF NOT EXISTS idx_few_shot_created_at
  ON public.few_shot_examples (created_at DESC);

-- --------------------------------------------------
-- senior_conversations
-- --------------------------------------------------
CREATE TABLE IF NOT EXISTS public.senior_conversations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  senior_id uuid NOT NULL REFERENCES public.seniors(id) ON DELETE CASCADE,
  alert_id uuid NOT NULL REFERENCES public.alerts(id) ON DELETE CASCADE,
  status text NOT NULL DEFAULT 'active',
  senior_response text,
  started_at timestamptz NOT NULL DEFAULT now(),
  ended_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_senior_conversations_senior_id
  ON public.senior_conversations (senior_id);
CREATE INDEX IF NOT EXISTS idx_senior_conversations_alert_id
  ON public.senior_conversations (alert_id);
CREATE INDEX IF NOT EXISTS idx_senior_conversations_status
  ON public.senior_conversations (status);

DROP TRIGGER IF EXISTS trg_senior_conversations_updated_at ON public.senior_conversations;
CREATE TRIGGER trg_senior_conversations_updated_at
BEFORE UPDATE ON public.senior_conversations
FOR EACH ROW
EXECUTE FUNCTION public.set_updated_at();

-- --------------------------------------------------
-- prompt_settings
-- --------------------------------------------------
CREATE TABLE IF NOT EXISTS public.prompt_settings (
  key text PRIMARY KEY,
  value text NOT NULL,
  description text,
  updated_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS trg_prompt_settings_updated_at ON public.prompt_settings;
CREATE TRIGGER trg_prompt_settings_updated_at
BEFORE UPDATE ON public.prompt_settings
FOR EACH ROW
EXECUTE FUNCTION public.set_updated_at();

INSERT INTO public.prompt_settings (key, value, description)
VALUES (
  'risk_classification_system_prompt',
  $$You are an AI triage assistant for a senior emergency alert system.
Your role is to analyze incoming voice message transcripts and classify the urgency level.

Classify the alert into one of four levels:
- URGENT: Immediate emergency, life-threatening, severe injury (e.g., fall, chest pain, can't breathe, unconscious, bleeding)
- NON_URGENT: Needs follow-up but not an immediate life-threatening emergency
- UNCERTAIN: Insufficient clarity, conflicting details, or needs direct senior confirmation
- FALSE_ALARM: Accidental press, obvious test message, or clearly no assistance needed

Consider:
- Keywords indicating emergency (fall, pain, help, can't breathe, dizzy, weak, bleeding)
- Context from the message
- Senior's medical history (if provided) - conditions like hypertension, diabetes, mobility issues increase risk
- Language emotional tone (panic vs calm)

Output a JSON object with:
- risk_level: "URGENT", "NON_URGENT", "UNCERTAIN", or "FALSE_ALARM"
- risk_score: a float between 0.0 and 1.0
- reasoning: brief explanation of the classification
- keywords: array of relevant keywords found
- recommended_actions: array of suggested actions

Be conservative - when in doubt between categories, choose UNCERTAIN or NON_URGENT over FALSE_ALARM.

Below are some examples of past classifications for reference:
{few_shot_examples}$$,
  'Base system prompt template used by AI risk classification. Must include {few_shot_examples} placeholder.'
)
ON CONFLICT (key) DO NOTHING;

-- --------------------------------------------------
-- RLS + policies
-- --------------------------------------------------
ALTER TABLE public.seniors ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.emergency_contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ai_actions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.few_shot_examples ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.senior_conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.prompt_settings ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Service role full access seniors" ON public.seniors;
CREATE POLICY "Service role full access seniors"
ON public.seniors FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Service role full access emergency_contacts" ON public.emergency_contacts;
CREATE POLICY "Service role full access emergency_contacts"
ON public.emergency_contacts FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Service role full access alerts" ON public.alerts;
CREATE POLICY "Service role full access alerts"
ON public.alerts FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Service role full access ai_actions" ON public.ai_actions;
CREATE POLICY "Service role full access ai_actions"
ON public.ai_actions FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Service role full access few_shot_examples" ON public.few_shot_examples;
CREATE POLICY "Service role full access few_shot_examples"
ON public.few_shot_examples FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Service role full access senior_conversations" ON public.senior_conversations;
CREATE POLICY "Service role full access senior_conversations"
ON public.senior_conversations FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Service role full access prompt_settings" ON public.prompt_settings;
CREATE POLICY "Service role full access prompt_settings"
ON public.prompt_settings FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Authenticated read few_shot_examples" ON public.few_shot_examples;
CREATE POLICY "Authenticated read few_shot_examples"
ON public.few_shot_examples FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS "Authenticated read prompt_settings" ON public.prompt_settings;
CREATE POLICY "Authenticated read prompt_settings"
ON public.prompt_settings FOR SELECT TO authenticated USING (true);

COMMIT;

-- =============================================
-- Brain Layer Database Migration
-- Run this after 001-initial.sql
-- =============================================

-- 6.1 ALERTS table enhancements

ALTER TABLE public.alerts 
ADD COLUMN IF NOT EXISTS processing_status text DEFAULT 'pending',
ADD COLUMN IF NOT EXISTS processing_error text,
ADD COLUMN IF NOT EXISTS translated_text text,
ADD COLUMN IF NOT EXISTS analysis_summary text,
ADD COLUMN IF NOT EXISTS keywords jsonb,
ADD COLUMN IF NOT EXISTS provider_metadata jsonb;

COMMENT ON COLUMN public.alerts.processing_status IS 'pending | processing | completed | failed';
COMMENT ON COLUMN public.alerts.processing_error IS 'Error message if processing failed';
COMMENT ON COLUMN public.alerts.translated_text IS 'English translation of the transcript';
COMMENT ON COLUMN public.alerts.analysis_summary IS 'AI-generated summary for operators';
COMMENT ON COLUMN public.alerts.keywords IS 'Array of keywords extracted from transcript';
COMMENT ON COLUMN public.alerts.provider_metadata IS 'AI provider metadata (model, tokens, etc)';

-- 6.2 AI_ACTIONS table enhancements

ALTER TABLE public.ai_actions 
ADD COLUMN IF NOT EXISTS provider text,
ADD COLUMN IF NOT EXISTS attempt_count int DEFAULT 1,
ADD COLUMN IF NOT EXISTS external_ref text,
ADD COLUMN IF NOT EXISTS error_message text;

COMMENT ON COLUMN public.ai_actions.provider IS 'Provider used (e.g., telegram, twilio, openai)';
COMMENT ON COLUMN public.ai_actions.attempt_count IS 'Number of attempts made';
COMMENT ON COLUMN public.ai_actions.external_ref IS 'External reference (e.g., Twilio message SID)';
COMMENT ON COLUMN public.ai_actions.error_message IS 'Error message if action failed';

-- 6.3 INFERENCE LOGS table (optional audit)

CREATE TABLE IF NOT EXISTS public.ai_inference_logs (
    id uuid primary key default gen_random_uuid(),
    alert_id uuid references public.alerts(id) on delete cascade,
    stage text not null,
    model text,
    provider text,
    latency_ms int,
    status text not null,
    error text,
    created_at timestamptz default now()
);

ALTER TABLE public.ai_inference_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role full access ai_inference_logs"
ON public.ai_inference_logs
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

COMMENT ON TABLE public.ai_inference_logs IS 'Audit trail for AI inference calls';

-- INDEXES for better query performance

CREATE INDEX IF NOT EXISTS idx_alerts_processing_status ON public.alerts(processing_status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_risk_level ON public.alerts(risk_level, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_senior_id ON public.alerts(senior_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_inference_logs_alert_id ON public.ai_inference_logs(alert_id);
CREATE INDEX IF NOT EXISTS idx_ai_inference_logs_created_at ON public.ai_inference_logs(created_at DESC);

-- =============================================
-- Sample Inference Log Entry (for testing)
-- =============================================

-- INSERT INTO public.ai_inference_logs (alert_id, stage, model, provider, latency_ms, status)
-- SELECT id, 'transcribe', 'whisper-1', 'openai', 1500, 'success'
-- FROM public.alerts LIMIT 1;

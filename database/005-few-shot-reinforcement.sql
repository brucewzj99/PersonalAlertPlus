-- 005-few-shot-reinforcement.sql
-- Table for storing operator-corrected examples for few-shot prompting

CREATE TABLE IF NOT EXISTS public.few_shot_examples (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    transcript TEXT NOT NULL,
    risk_level TEXT NOT NULL CHECK (risk_level IN ('URGENT', 'NON_URGENT', 'UNCERTAIN', 'FALSE_ALARM')),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for faster retrieval of latest examples
CREATE INDEX idx_few_shot_created_at ON public.few_shot_examples (created_at DESC);

-- Enable RLS
ALTER TABLE public.few_shot_examples ENABLE ROW LEVEL SECURITY;

-- Service role access
CREATE POLICY "Service role has all access" ON public.few_shot_examples
    FOR ALL USING (true);

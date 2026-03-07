-- Senior conversation tracking for urgent/non-urgent follow-up
CREATE TABLE IF NOT EXISTS senior_conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    senior_id UUID NOT NULL REFERENCES seniors(id) ON DELETE CASCADE,
    alert_id UUID NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    senior_response TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_senior_conversations_senior_id ON senior_conversations(senior_id);
CREATE INDEX idx_senior_conversations_alert_id ON senior_conversations(alert_id);
CREATE INDEX idx_senior_conversations_status ON senior_conversations(status);

ALTER TABLE senior_conversations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own senior conversations" ON senior_conversations
    FOR SELECT USING (true);
CREATE POLICY "Service role can manage senior conversations" ON senior_conversations
    FOR ALL USING (true) WITH CHECK (true);


ALTER TABLE alerts ADD COLUMN IF NOT EXISTS senior_response TEXT;
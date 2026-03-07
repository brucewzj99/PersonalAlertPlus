-- Add columns to track operator interventions and resolution status
ALTER TABLE alerts 
ADD COLUMN IF NOT EXISTS ambulance_dispatched BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS family_called BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS is_resolved BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS operator_notes TEXT;

-- Index for performance on the dashboard feed
CREATE INDEX IF NOT EXISTS idx_alerts_is_resolved ON alerts(is_resolved);

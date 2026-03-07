-- Add is_attended column to track if a case is being handled by an operator
ALTER TABLE alerts 
ADD COLUMN IF NOT EXISTS is_attended BOOLEAN DEFAULT FALSE;

-- Index for filtering
CREATE INDEX IF NOT EXISTS idx_alerts_is_attended ON alerts(is_attended);

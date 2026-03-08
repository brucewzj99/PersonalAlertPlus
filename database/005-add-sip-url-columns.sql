-- =============================================
-- 005-add-sip-url-columns.sql
-- Add SIP URL fields for click-to-call actions.
-- =============================================

BEGIN;

ALTER TABLE public.seniors
  ADD COLUMN IF NOT EXISTS sip_url text;

ALTER TABLE public.emergency_contacts
  ADD COLUMN IF NOT EXISTS sip_url text;

COMMIT;

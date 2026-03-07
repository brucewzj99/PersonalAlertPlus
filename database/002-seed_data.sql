--------------------------------------------------
-- 1️⃣ SEED SENIORS
--------------------------------------------------
insert into public.seniors (
  id,
  full_name,
  phone_number,
  telegram_user_id,
  address,
  birth_year,
  birth_month,
  birth_day,
  preferred_language,
  medical_notes
)
values
(
  gen_random_uuid(),
  'Tan Ah Kow',
  '+6591111111',
  'tg_ahkow_001',
  'Block 123 Toa Payoh Lorong 1 #05-123',
  1947,
  1,
  1,
  'zh',
  'Hypertension, mild mobility issues'
),
(
  gen_random_uuid(),
  'Mdm Siti Rahmah',
  '+6592222222',
  'tg_siti_002',
  'Block 456 Bedok North Ave 3 #02-456',
  1943,
  1,
  1,
  'ms',
  'Diabetes, lives alone'
);

--------------------------------------------------
-- 2️⃣ SEED EMERGENCY CONTACTS
--------------------------------------------------

insert into public.emergency_contacts (
  senior_id,
  name,
  relationship,
  phone_number,
  telegram_user_id,
  priority_order,
  notify_on_uncertain
)
select id, 'Tan Wei Ming', 'Son', '+6588881111', 'tg_weiming', 1, true
from public.seniors where full_name = 'Tan Ah Kow';

insert into public.emergency_contacts (
  senior_id,
  name,
  relationship,
  phone_number,
  telegram_user_id,
  priority_order,
  notify_on_uncertain
)
select id, 'Nur Aisyah', 'Daughter', '+6588882222', 'tg_aisyah', 1, false
from public.seniors where full_name = 'Mdm Siti Rahmah';

--------------------------------------------------
-- 3️⃣ SEED ALERTS
--------------------------------------------------

-- FALSE ALARM example
insert into public.alerts (
  id,
  senior_id,
  channel,
  audio_url,
  transcription,
  language_detected,
  risk_level,
  risk_score,
  status,
  requires_operator,
  resolved_by
)
select
  gen_random_uuid(),
  id,
  'telegram',
  'https://storage.supabase.co/audio/sample_low.mp3',
  'Hello I pressed by mistake, I am okay.',
  'English',
  'FALSE_ALARM',
  0.15,
  'closed',
  false,
  'ai'
from public.seniors where full_name = 'Tan Ah Kow';


-- URGENT example
insert into public.alerts (
  id,
  senior_id,
  channel,
  audio_url,
  transcription,
  language_detected,
  risk_level,
  risk_score,
  status,
  requires_operator,
  resolved_by
)
select
  gen_random_uuid(),
  id,
  'telegram',
  'https://storage.supabase.co/audio/sample_high.mp3',
  'I fell down and cannot get up. Very pain.',
  'English',
  'URGENT',
  0.94,
  'escalated',
  true,
  'operator'
from public.seniors where full_name = 'Mdm Siti Rahmah';

--------------------------------------------------
-- 4️⃣ SEED AI ACTIONS
--------------------------------------------------

-- FALSE ALARM AI actions
insert into public.ai_actions (
  alert_id,
  action_type,
  action_status,
  details
)
select
  a.id,
  'notify_family',
  'success',
  jsonb_build_object('method','telegram','message','False alarm detected. Senior confirmed safe.')
from public.alerts a
where a.risk_level = 'FALSE_ALARM';

insert into public.ai_actions (
  alert_id,
  action_type,
  action_status,
  details
)
select
  a.id,
  'auto_call_senior',
  'success',
  jsonb_build_object('call_status','answered','response','Senior confirmed safe.')
from public.alerts a
where a.risk_level = 'FALSE_ALARM';


-- URGENT AI action
insert into public.ai_actions (
  alert_id,
  action_type,
  action_status,
  details
)
select
  a.id,
  'escalate_to_operator',
  'success',
  jsonb_build_object('reason','Urgent confidence fall detection')
from public.alerts a
where a.risk_level = 'URGENT';

--------------------------------------------------
-- 5️⃣ SEED OPERATOR ACTION
--------------------------------------------------

insert into public.operator_actions (
  alert_id,
  operator_id,
  ai_recommendation,
  operator_decision,
  decision_notes,
  ai_accuracy_rating,
  overridden
)
select
  a.id,
  (select id from auth.users limit 1),
  'Dispatch ambulance immediately',
  'Ambulance dispatched',
  'Senior confirmed fall. SCDF notified.',
  5,
  false
from public.alerts a
where a.risk_level = 'URGENT';

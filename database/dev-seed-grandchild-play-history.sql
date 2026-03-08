-- Dev seed: historical false alarms for one senior + one current urgent escalation.
-- Purpose: help AI operator-action recommendation pick up a "grandchild pressed button" pattern
-- while still prioritizing urgent handling when senior explicitly indicates "I need help".

BEGIN;

-- Target senior from your provided row.
WITH target_senior AS (
  SELECT id
  FROM public.seniors
  WHERE id = '51ea1a42-8485-4dd3-9e2c-2ebbe920c02e'
)
INSERT INTO public.alerts (
  id,
  senior_id,
  channel,
  transcription,
  translated_text,
  language_detected,
  risk_level,
  risk_score,
  status,
  requires_operator,
  resolved_by,
  processing_status,
  analysis_summary,
  keywords,
  senior_response,
  is_resolved,
  created_at
)
SELECT
  v.id,
  ts.id,
  'telegram',
  v.transcription,
  v.translated_text,
  'yue',
  v.risk_level,
  v.risk_score,
  v.status,
  v.requires_operator,
  v.resolved_by,
  'completed',
  v.analysis_summary,
  v.keywords::jsonb,
  v.senior_response,
  v.is_resolved,
  v.created_at
FROM target_senior ts
CROSS JOIN (
  VALUES
    (
      '0d6f0e2b-ef42-4d85-b30f-7dbd6c8be001'::uuid,
      'My grandson was playing and pressed the emergency button by mistake. I am okay.',
      'My grandson was playing and pressed the emergency button by mistake. I am okay.',
      'FALSE_ALARM',
      0.10::numeric,
      'closed',
      false,
      'operator',
      'Likely accidental trigger. Senior confirms no assistance needed; recurring child-play pattern noted.',
      '["accidental", "grandson", "button press", "no injury"]',
      '[senior confirmed okay]',
      true,
      now() - interval '21 days'
    ),
    (
      '0d6f0e2b-ef42-4d85-b30f-7dbd6c8be002'::uuid,
      'No emergency. My grandchild pressed the alert button while visiting.',
      'No emergency. My grandchild pressed the alert button while visiting.',
      'FALSE_ALARM',
      0.12::numeric,
      'closed',
      false,
      'operator',
      'Repeated accidental activation by grandchild; no medical issue reported.',
      '["false alarm", "grandchild", "accidental activation"]',
      '[senior confirmed okay]',
      true,
      now() - interval '14 days'
    ),
    (
      '0d6f0e2b-ef42-4d85-b30f-7dbd6c8be003'::uuid,
      'The kid touched it again. Sorry, I do not need help now.',
      'The kid touched it again. Sorry, I do not need help now.',
      'FALSE_ALARM',
      0.08::numeric,
      'closed',
      false,
      'operator',
      'Historical pattern: child-triggered false alarm; explicitly denied need for assistance.',
      '["child play", "accidental", "no assistance"]',
      '[senior confirmed okay]',
      true,
      now() - interval '7 days'
    ),
    (
      '0d6f0e2b-ef42-4d85-b30f-7dbd6c8be004'::uuid,
      'I have issues now. I feel chest tightness and dizziness. Please help.',
      'I have issues now. I feel chest tightness and dizziness. Please help.',
      'URGENT',
      0.93::numeric,
      'escalated',
      true,
      null,
      'Senior explicitly requested help; urgent symptoms override historical false-alarm pattern.',
      '["i need help", "chest tightness", "dizziness", "urgent"]',
      '[senior escalated via callback: i have issues]',
      false,
      now() - interval '5 minutes'
    )
) AS v(
  id,
  transcription,
  translated_text,
  risk_level,
  risk_score,
  status,
  requires_operator,
  resolved_by,
  analysis_summary,
  keywords,
  senior_response,
  is_resolved,
  created_at
)
ON CONFLICT (id) DO UPDATE SET
  transcription = EXCLUDED.transcription,
  translated_text = EXCLUDED.translated_text,
  risk_level = EXCLUDED.risk_level,
  risk_score = EXCLUDED.risk_score,
  status = EXCLUDED.status,
  requires_operator = EXCLUDED.requires_operator,
  resolved_by = EXCLUDED.resolved_by,
  processing_status = EXCLUDED.processing_status,
  analysis_summary = EXCLUDED.analysis_summary,
  keywords = EXCLUDED.keywords,
  senior_response = EXCLUDED.senior_response,
  is_resolved = EXCLUDED.is_resolved,
  created_at = EXCLUDED.created_at;

-- Optional audit trail records in ai_actions for realism.
INSERT INTO public.ai_actions (alert_id, action_type, action_status, details, created_at)
VALUES
  (
    '0d6f0e2b-ef42-4d85-b30f-7dbd6c8be001',
    'senior_confirmed_ok',
    'success',
    '{"reason":"Senior confirmed accidental press by grandson"}'::jsonb,
    now() - interval '21 days' + interval '2 minutes'
  ),
  (
    '0d6f0e2b-ef42-4d85-b30f-7dbd6c8be002',
    'senior_confirmed_ok',
    'success',
    '{"reason":"Grandchild play scenario repeated"}'::jsonb,
    now() - interval '14 days' + interval '2 minutes'
  ),
  (
    '0d6f0e2b-ef42-4d85-b30f-7dbd6c8be003',
    'senior_confirmed_ok',
    'success',
    '{"reason":"Accidental trigger by child"}'::jsonb,
    now() - interval '7 days' + interval '2 minutes'
  ),
  (
    '0d6f0e2b-ef42-4d85-b30f-7dbd6c8be004',
    'senior_escalated_to_urgent',
    'success',
    '{"reason":"Senior clicked I have issues"}'::jsonb,
    now() - interval '4 minutes'
  )
ON CONFLICT DO NOTHING;

COMMIT;

-- Quick check query:
-- SELECT id, risk_level, status, requires_operator, transcription, created_at
-- FROM public.alerts
-- WHERE senior_id = '51ea1a42-8485-4dd3-9e2c-2ebbe920c02e'
-- ORDER BY created_at DESC
-- LIMIT 8;

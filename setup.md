# PersonalAlertPlus Brain Layer - Setup & Implementation Plan

## 1) Objective

Build the AI "brain" layer in Python on top of the existing Telegram bot layer so that:

- Telegram bot sends alert payload (`senior_id`, `telegram_user_id`, `channel`, `audio_url` or `text`) to brain endpoint.
- Brain fetches voice file from Supabase Storage when `audio_url` is present.
- Brain performs:
  - speech-to-text (OpenAI Whisper API)
  - language detection
  - translation to English (via OpenAI-compatible chat model)
  - urgency/risk classification (URGENT/NON_URGENT/UNCERTAIN/FALSE_ALARM + score + rationale)
  - action generation (store actions + notify family)
- Brain writes all outputs to Supabase tables (`alerts`, `ai_actions`, etc.).
- Hackathon-first architecture: one command starts both Telegram layer + brain API in one process.

---

## 2) Confirmed Product Decisions

- STT provider: **OpenAI Whisper API**
- LLM strategy: **OpenAI-compatible API standard** (supports OpenAI, OpenRouter, Groq-compatible endpoints by config)
- Translation: **same LLM** used for analysis
- Medium-risk automated call: **defer post-hackathon**
- Family notification: **Telegram + SMS fallback**
- Dashboard: **not in scope**; AI output persisted to Supabase for downstream consumption

---

## 3) Runtime Topology (Hackathon)

**Chosen approach: single service, single command**

Run one FastAPI app that includes:
- Existing Telegram webhook/polling handling
- Brain ingestion endpoint
- Brain processing services

Command: `python main.py`

---

## 4) Pre-Requisites

### 4.1 Accounts / External Services

- Telegram Bot token (already configured)
- Supabase project with:
  - Postgres
  - Storage bucket (`alerts-audio`)
  - Service role key
- AI provider key (OpenAI-compatible) - **to be provided**
- SMS provider key (Twilio) - **to be provided**

### 4.2 Python & Tooling

- Python 3.11+
- Virtualenv setup
- Dependencies installable via `requirements.txt`

### 4.3 Supabase Storage Accessibility

- Private bucket + service role authenticated download preferred
- Public URL fallback for hackathon

---

## 5) Environment Variables Required

```env
# Existing
TELEGRAM_BOT_TOKEN=
SUPABASE_URL=
SUPABASE_SECRET_KEY=
SUPABASE_AUDIO_BUCKET=alerts-audio
BACKEND_API_URL=http://127.0.0.1:8000/api/v1/brain/alerts/ingest
BOT_MODE=polling
BOT_WEBHOOK_URL=
BOT_WEBHOOK_SECRET=

# Brain / AI provider (OpenAI-compatible)
AI_API_BASE_URL=https://api.openai.com/v1
AI_API_KEY=
AI_CHAT_MODEL=gpt-4o-mini
AI_TRANSCRIPTION_MODEL=whisper-1
AI_REQUEST_TIMEOUT_SECONDS=30

# Optional model behavior tuning
AI_MAX_RETRIES=3
AI_TEMPERATURE=0.1

# SMS fallback
SMS_PROVIDER=twilio
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=
TWILIO_MESSAGING_SERVICE_SID=

# Brain app behavior
BRAIN_PROCESSING_TIMEOUT_SECONDS=45
BRAIN_ENABLE_SMS_FALLBACK=true
BRAIN_NOTIFY_TELEGRAM_FIRST=true
```

---

## 6) Database Changes

### 6.1 `alerts` table enhancements

Add fields:
- `processing_status text default 'pending'` (values: pending | processing | completed | failed)
- `processing_error text null`
- `translated_text text null`
- `analysis_summary text null`
- `keywords jsonb null`
- `provider_metadata jsonb null`

### 6.2 `ai_actions` table enhancement

Add:
- `provider text null`
- `attempt_count int default 1`
- `external_ref text null`
- `error_message text null`

### 6.3 Audit table (optional)

Create `ai_inference_logs` for debugging.

---

## 7) API Contract

### 7.1 Ingestion endpoint

`POST /api/v1/brain/alerts/ingest`

Request:
```json
{
  "senior_id": "uuid",
  "telegram_user_id": "string",
  "channel": "telegram",
  "audio_url": "https://...",
  "text": "optional text"
}
```

Response:
```json
{
  "ok": true,
  "alert_id": "uuid",
  "processing_status": "completed",
  "risk_level": "URGENT",
  "risk_score": 0.93
}
```

### 7.2 Health endpoint

`GET /api/v1/brain/health`

---

## 8) Brain Processing Pipeline

1. **Normalize input** - validate payload, create alert row with `processing_status='processing'`
2. **Hydrate context** - fetch senior profile and emergency contacts
3. **Acquire content** - download audio from Supabase or use text directly
4. **Transcription** - call Whisper API
5. **Language handling** - detect language, translate to English if needed
6. **Risk analysis** - LLM structured output with risk_level, score, reasoning, keywords
7. **Guardrails** - apply keyword-based overrides (e.g., "fall" always escalates to URGENT)
8. **Persistence** - update alert row with transcription, translation, risk level, summary
9. **Family notification** - notify emergency contacts via Telegram → SMS fallback
10. **Senior confirmation** - send message to senior with:
    - Risk level detected
    - Native language + English text
    - Confirmation/Escalate inline buttons (for UNCERTAIN and FALSE_ALARM)
11. **Error handling** - stage-level try/except, preserve partial outcomes

---

## 8b) Senior Confirmation & Escalation Flow

After AI processing, seniors receive a confirmation message:

```
✅ Status Update

_我们已经收到您的信息，经评估确认一切正常。_

---

We received your message and assessed everything is fine.
```

For **UNCERTAIN** risk, inline buttons are included:
- "I am okay" and "Escalate"

For **FALSE_ALARM** risk, an inline button is included:
- "Escalate"

If senior clicks the button:
1. Alert is escalated to NON_URGENT risk
2. Alert status set to `escalated`, `requires_operator=true`
3. Emergency contacts notified again with "SENIOR ESCALATED" message
4. Senior receives confirmation message

---

## 9) Code Structure

```
app/
├── brain/
│   ├── __init__.py
│   ├── router.py          # FastAPI endpoints
│   ├── schemas.py         # request/response + AI output schemas
│   ├── orchestrator.py    # end-to-end pipeline
│   ├── prompts.py         # classification & translation prompts
│   ├── providers/
│   │   ├── __init__.py
│   │   └── openai_compatible.py  # unified client (Whisper + Chat)
│   └── services/
│       ├── __init__.py
│       ├── audio_fetcher.py      # download audio from Supabase
│       ├── risk_engine.py         # classification guardrails
│       ├── notification_service.py # Telegram + Twilio SMS
│       └── action_logger.py       # log to ai_actions table
├── bot/
│   └── handlers/
│       ├── escalate.py    # confirm/escalate callback handler
│       └── ...
```

---

## 10) Senior Confirmation Messages

Messages are sent in senior's native language + English:

| Language | FALSE_ALARM | UNCERTAIN | NON_URGENT | URGENT |
|----------|-------------|-----------|------------|--------|
| EN | "Sorry... tap Escalate" | "Please confirm if you are okay" | "Family notified; escalated as NON_URGENT" | "Escalated to operations as URGENT priority" |
| ZH | "抱歉...可点击升级处理" | "请确认是否平安" | "家属已通知，非紧急升级" | "已按紧急优先级升级" |
| MS | "Maaf... tekan Eskalasi" | "Sila sahkan anda okay" | "Keluarga dimaklumkan, bukan kecemasan" | "Dinaikkan sebagai keutamaan segera" |
| TA | "மன்னிக்கவும்... Escalate அழுத்தவும்" | "நீங்கள் நலமா உறுதிசெய்யவும்" | "குடும்பம் அறிவிக்கப்பட்டது, NON_URGENT" | "அவசர முன்னுரிமையுடன் உயர்த்தப்பட்டது" |

---

## 11) Testing Plan

- Unit tests for validation and risk logic
- Integration tests for end-to-end processing
- Manual UAT with sample audios (FALSE_ALARM/URGENT/non-English scenarios)

---

## 12) Implementation Phases

1. **Phase 0** - Foundation (config, schemas, dependencies)
2. **Phase 1** - Brain endpoint with basic validation
3. **Phase 2** - AI provider abstraction (OpenAI-compatible client)
4. **Phase 3** - Pipeline orchestration (STT, translation, classification)
5. **Phase 4** - Notifications (Telegram + SMS fallback)
6. **Phase 5** - Hardening (retries, timeouts, error handling)
7. **Phase 6** - QA and demo readiness

---

## 13) Definition of Done

- Telegram bot submits payload to brain endpoint
- Brain processes text and voice alerts end-to-end
- Voice pipeline: STT + translation + risk classification
- Risk output persisted in `alerts` table
- AI actions persisted in `ai_actions` table
- Family notification via Telegram with SMS fallback
- Senior confirmation message sent (native language + English)
- Confirmation/Escalate inline buttons for UNCERTAIN/FALSE_ALARM flows
- Escalation callback works when senior clicks button
- Debug print statements show processing stages
- One command starts full system
- Error cases persisted (no silent failures)

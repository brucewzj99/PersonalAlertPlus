🛡 PersonalAlertPlus
AI-Assisted Digital Extension for GovTech Personal Alert Button (PAB)

---

## 1. 📌 Project Overview

* PersonalAlertPlus is an AI-assisted triage layer designed to extend Singapore’s official Personal Alert Button (PAB) system with intelligent digital channels.

* This project expands on GovTech’s PAB platform:

  * 🔗 [https://www.developer.tech.gov.sg/products/categories/sensor-platforms-and-internet-of-things/pab/overview](https://www.developer.tech.gov.sg/products/categories/sensor-platforms-and-internet-of-things/pab/overview)

* The official PAB:

  * Is a hardware-based emergency alert device
  * Installed in seniors’ homes
  * Sends a 10-second recording to a response centre when pressed
  * Includes senior tagging and address metadata

* PersonalAlertPlus extends this infrastructure by:

  * Adding Telegram-based emergency triggers
  * Automating transcription and triage
  * Assisting operators with urgency scoring
  * Reducing workload for non-critical alerts
  * Accelerating response for critical emergencies

* PersonalAlertPlus does not replace PAB.

* It enhances accessibility and triage efficiency.

---

## 2. 🎯 Problem Statement

* While the PAB system is effective, several operational challenges exist:

  * Seniors may not be near the hardware button
  * Operators must manually interpret raw audio
  * Language and dialect differences complicate assessment
  * High volume of accidental or NON_URGENT alerts
  * No automated triage assistance layer

* We aim to:

  * Extend emergency triggering beyond physical hardware
  * Use AI to assist operator decision-making
  * Improve emergency response time
  * Reduce unnecessary escalation
  * Introduce structured feedback for continuous improvement

---

## 3. 🧠 Core Solution

* PersonalAlertPlus introduces:

### 🔹 Digital Emergency Channel

* Seniors can:

  * Send a Telegram voice message
  * Trigger an emergency from anywhere
  * Automatically attach profile metadata

* This acts as a digital redundancy layer to the hardware PAB.

### 🔹 AI Processing Pipeline

* Upon receiving voice input:

  * Speech-to-text transcription
  * Language detection
  * Keyword extraction
  * Emergency classification
  * Confidence scoring

* Alerts are categorized into:

  * 🔴 URGENT – Immediate emergency
  * 🟠 NON_URGENT – Follow-up needed
  * 🟡 UNCERTAIN – Needs senior confirmation
  * 🟢 FALSE_ALARM – Accidental/no service request

### 🔹 AI Action Layer

* Based on classification:

* FALSE_ALARM

  * Reply with apology + option to escalate
  * Do not notify family by default
  * No operator required unless senior escalates

* UNCERTAIN

  * Reply to senior with bilingual confirmation message
  * Show inline buttons: "I am okay" and "Escalate"
  * Create a short follow-up conversation window for senior replies
  * Notify only contacts with `notify_on_uncertain = true`
  * If senior escalates, route to NON_URGENT flow and notify family

* NON_URGENT

  * Notify family
  * Escalate to operations as NON_URGENT
  * Mark case for operator follow-up
  * Ask senior for extra details via follow-up prompt with a "Skip" button

* URGENT

  * Notify family immediately
  * Escalate to operations as URGENT priority
  * Mark case for urgent operator handling
  * Ask senior for extra details via follow-up prompt with a "Skip" button

* Follow-up timeout safety net

  * Active follow-up conversations are checked every 5 seconds
  * If an UNCERTAIN conversation times out, system triggers a Twilio check-in voice call

* AI assists. Humans decide.

### 🔹 Operator Dashboard

* Operators can:

  * View live alerts
  * See transcription + language
  * View risk score & reasoning
  * View AI assessment details (`ai_assessment`), confidence score, and flagged keywords
  * Confirm or override AI decision
  * Close a case directly from the case details view
  * Add a case directly into `few_shot_examples` with one click
  * Manage emergency contacts in a dedicated pop-up interface
  * View senior medical notes during contact management
  * Edit base AI risk prompt in a Settings tab
  * Log structured case actions (dispatch ambulance / call family / mark attended) with explicit action timestamps
  * Choose dispatch destination when logging `dispatch_ambulance`
  * Select contacted family members as multi-select pill options when logging `call_family`
  * Review senior follow-up replies (including translated text and voice attachments)
  * Send multilingual senior updates when operator logs key actions (family called / response dispatched / attended)

* This builds a supervised AI improvement cycle.

---

## 4. 🏗 System Architecture

* Components:

  * Telegram Bot → Senior trigger channel
  * FastAPI Backend → AI processing & orchestration
  * Conversation Timeout Scheduler → periodic timeout checks (`senior_conversations`)
  * Supabase (Postgres + RLS) → Secure data storage
  * Twilio → SMS fallback + timeout safety check-in calls
  * React + Vite Dashboard → Operator interface
  * (Optional) ClickHouse → Analytics layer

---

## 4b. 🤖 Telegram Bot Features

### Registration Flow (`/start`)

When a senior first contacts the bot, they go through a step-by-step registration:

1. **Language Selection** - User selects preferred language from 6 options:
   - English, 中文 (Chinese), Bahasa Melayu (Malay), தமிழ் (Tamil), Hokkien, Cantonese
   
2. **Required Fields** (all subsequent prompts in selected language):
   - Full Name (2-100 characters)
   - Phone Number (8 digits, auto-adds +65)
   - Address (10-500 characters)
   - Birth Year (must be 18+ years old)
   - Birth Month (1-12)
   - Birth Day (valid for selected month)

3. **Optional Field**:
   - Medical Notes (max 2000 characters, with Skip option)

### Profile Management (`/profile`)

Registered seniors can view and update their profile:

- **View Profile**: Shows all details (name, phone, address, birthday, language, medical notes)
- **Update Options**: Inline buttons to update:
  - Phone Number
  - Address
  - Medical Notes
- All updates include input validation

### Alert Submission

After registration, seniors can send:
- **Voice messages** - Uploaded to Supabase Storage, alert record created, forwarded to backend API
- **Text messages** - Alert record created with transcription, forwarded to backend API

**Note:** Bot does NOT send immediate "alert received" message. Instead, the Brain layer sends a confirmation message with the risk assessment after processing.

### Senior Confirmation & Escalation

After AI processing, seniors receive a confirmation message:
- Shows risk level detected
- Written in their **native language** + **English**
- For UNCERTAIN risk: includes "I am okay" and "Escalate" inline buttons
- For FALSE_ALARM risk: includes "Escalate" inline button
- For URGENT/NON_URGENT risk: includes follow-up prompt + "Skip" button
- When senior clicks "Escalate":
  - Alert is escalated to NON_URGENT
  - Emergency contacts are notified immediately
  - Alert marked for operator review

### Senior Follow-Up Conversation

- For UNCERTAIN, URGENT, and NON_URGENT, system opens a `senior_conversations` record
- Senior can reply in text or voice; voice replies are transcribed and translated to English for operators
- Senior can explicitly skip via callback (`skip_follow_up:{alert_id}`)
- If no reply arrives before timeout:
  - conversation is marked as `timeout`
  - for UNCERTAIN only, system triggers a Twilio safety check-in call
  - timeout and call outcomes are logged in `ai_actions`

This provides a safety net in case AI misclassifies the situation.

---

## 5. 🔄 Alert Workflow

### Step 1 – Trigger

* Senior sends Telegram voice or text message.

### Step 2 – Ingestion

* Backend:

  * Stores metadata
  * Retrieves senior profile
  * Links to address and medical notes

### Step 3 – AI Processing

* Transcription
* Language detection
* Translation-quality guardrail (if translation looks suspicious, downgrade NON_URGENT to UNCERTAIN)
* Risk classification
* Confidence scoring

### Step 4 – AI Decision

* FALSE_ALARM → Reply with apology + Escalate option
* UNCERTAIN → Ask for confirmation ("I am okay" / "Escalate") + open follow-up conversation
* NON_URGENT → Notify family + escalate to operator as NON_URGENT + request follow-up details ("Skip" available)
* URGENT → Notify family + escalate to operator as URGENT priority + request follow-up details ("Skip" available)

### Step 4b – Follow-Up Timeout Safety Net

* Scheduler checks active conversations every 5 seconds
* If UNCERTAIN follow-up times out:

  * Mark conversation as `timeout`
  * Trigger Twilio check-in voice call
  * Log timeout/call actions to `ai_actions`

### Step 5 – Operator Review

* Operator:

  * Reviews recommendation
  * Confirms dispatch or override
  * Can close case directly in operator workflow
  * Logs decision and actions to `public.operator_actions` with `action_time` (default now)
  * Captures who was contacted for family-call actions in `action_payload`
  * Rates AI accuracy

### Step 6 – Feedback Loop

* Operator feedback stored for:

  * Performance tracking
  * Future model refinement
  * System reliability metrics

---

## 5b. 📊 Alert Data Flow

```mermaid
flowchart TD
A1[Senior sends voice/text] --> A2[Telegram bot handlers]
A2 --> A3[Create alert row in alerts]
A2 --> A4[POST /api/v1/brain/alerts/ingest]

A4 --> B1[BrainOrchestrator]
B1 --> B2[Load senior + emergency contacts]
B1 --> B3[Transcribe/translate if needed]
B1 --> B4[Classify risk + guardrails]
B1 --> B5[Update alerts with risk + ai_assessment]

B4 --> C1{Risk level}
C1 -->|URGENT| C2[Notify contacts + escalate]
C1 -->|NON_URGENT| C3[Notify contacts + escalate]
C1 -->|UNCERTAIN| C4[Notify only contacts flagged notify_on_uncertain]
C1 -->|FALSE_ALARM| C5[No default contact notification]

C2 --> D1[Send senior follow-up audio + Skip button]
C3 --> D1
C4 --> D2[Send senior confirmation buttons: I am okay / Escalate]
C5 --> D3[Send senior Escalate button]

D1 --> E1[Create senior_conversations active]
D2 --> E1

E1 --> F1[Senior sends text/voice follow-up]
F1 --> F2[Store translated reply + optional audio URL]
F2 --> F3[Set requires_operator true]

E1 --> G1[Scheduler checks timeout every 5s]
G1 -->|UNCERTAIN timeout| G2[Mark timeout + trigger Twilio check-in call]
G1 -->|Other timeout| G3[Mark timeout only]

H1[Operator dashboard override/close] --> H2[PATCH /api/v1/operator/alerts/{id}/override]
H2 --> H3[Insert rows into operator_actions]
H2 --> H4[Optional senior operator-action update voice/text]

subgraph Supabase
  S1[(seniors)]
  S2[(emergency_contacts)]
  S3[(alerts)]
  S4[(ai_actions)]
  S5[(operator_actions)]
  S6[(senior_conversations)]
  S7[(few_shot_examples)]
  S8[(prompt_settings)]
end

B2 --> S1
B2 --> S2
A3 --> S3
B5 --> S3
C2 --> S4
C3 --> S4
C4 --> S4
C5 --> S4
F2 --> S4
F2 --> S6
G2 --> S4
G3 --> S6
H3 --> S5
```

### Bot → Backend API Payload

When the bot receives an alert, it sends this payload to the backend:

```json
{
  "alert_id": "uuid",
  "senior_id": "uuid",
  "telegram_user_id": "string",
  "channel": "telegram",
  "audio_url": "https://... (optional)",
  "audio_base64": "optional-base64 (optional)",
  "text": "string (optional)"
}
```

The backend retrieves senior details (name, phone, address, medical notes) using the `senior_id`.

---

## 6. 🗄 Database Design

* Fresh-start bootstrap SQL is provided at `database/000-master.sql`.
* Migration rule: never modify historical migration files; append new numbered migrations only.
* Latest additive migrations for operator action logging:

  * `database/001-operator-actions-table-and-backfill.sql` → adds `public.operator_actions`, backfills legacy action flags, keeps compatibility trigger
  * `database/002-remove-legacy-alert-action-columns.sql` → removes legacy action flag columns from `public.alerts` once app migration is complete
  * `database/003-add-alert-ai-assessment-column.sql` → adds `ai_assessment` in `public.alerts` for concise reasoning display in operator dashboard

* Core Tables:

  * seniors
  * emergency_contacts
  * alerts
  * ai_actions
  * operator_actions
  * few_shot_examples
  * senior_conversations
  * prompt_settings

---

### 6.1 📋 Seniors Table (`public.seniors`)

Registered seniors profile information.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | uuid | Yes | Auto-generated primary key |
| full_name | text | Yes | Senior's full name |
| phone_number | text | Yes | Singapore format (+65XXXXXXXX), unique |
| telegram_user_id | text | No | Telegram user ID (for bot auth) |
| address | text | Yes | Residential address |
| birth_year | int | No | Year of birth (YYYY) |
| birth_month | int | No | Month of birth (1-12) |
| birth_day | int | No | Day of birth (1-31) |
| preferred_language | text | No | en/zh/ms/ta/nan/yue |
| medical_notes | text | No | Medical conditions/notes (max 2000 chars) |
| created_at | timestamptz | Yes | Registration timestamp (auto-generated) |

---

### 6.2 👥 Emergency Contacts Table (`public.emergency_contacts`)

Contacts to notify in case of emergency.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | uuid | Yes | Auto-generated primary key |
| senior_id | uuid | Yes | Foreign key to seniors(id) |
| name | text | Yes | Contact's full name |
| relationship | text | No | Relationship to senior (e.g., Son, Daughter) |
| phone_number | text | No | Contact's phone number |
| telegram_user_id | text | No | Contact's Telegram user ID |
| priority_order | int | No | Contact priority (1 = highest) |
| notify_on_uncertain | bool | No | Whether this contact receives UNCERTAIN alerts |
| created_at | timestamptz | Yes | Creation timestamp |

---

### 6.3 🚨 Alerts Table (`public.alerts`)

Emergency alerts triggered by seniors.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | uuid | Yes | Auto-generated primary key |
| senior_id | uuid | Yes | Foreign key to seniors(id) |
| channel | text | Yes | Source channel (telegram/sms/whatsapp) |
| audio_url | text | No | URL to voice message in Supabase Storage |
| transcription | text | No | Text content or voice-to-text result |
| language_detected | text | No | Detected language (en/zh/ms/ta/etc) |
| translated_text | text | No | English translation of transcript |
| risk_level | text | No | URGENT/NON_URGENT/UNCERTAIN/FALSE_ALARM classification |
| risk_score | numeric | No | AI confidence score (0.0-1.0) |
| ai_assessment | text | No | Concise AI reasoning text shown to operators |
| analysis_summary | text | No | AI-generated summary for operators |
| keywords | jsonb | No | Array of keywords extracted |
| status | text | No | pending/pending_confirmation/escalated/closed |
| requires_operator | boolean | No | Whether operator intervention needed |
| senior_response | text | No | Latest English-normalized follow-up response from senior |
| is_resolved | boolean | No | Whether case is resolved/closed |
| resolved_by | text | No | Who resolved (ai/operator) |
| processing_status | text | No | pending/processing/completed/failed |
| processing_error | text | No | Error message if processing failed |
| created_at | timestamptz | Yes | Alert creation timestamp |

* Note: operator intervention details are modeled in `public.operator_actions` as generic action rows with timestamps and payload metadata. Legacy action booleans may still exist in transitional environments, but the app treats `operator_actions` as source of truth.

---

### 6.4 🤖 AI Actions Table (`public.ai_actions`)

Automated AI-triggered actions based on risk assessment.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | uuid | Yes | Auto-generated primary key |
| alert_id | uuid | Yes | Foreign key to alerts(id) |
| action_type | text | Yes | Type of action (e.g. notify_family, senior_escalated_to_non_urgent, senior_conversation_reply, conversation_timeout, checkin_call) |
| action_status | text | No | pending/success/failed (default: pending) |
| details | jsonb | No | Action-specific data (method, message, etc) |
| provider | text | No | Provider used (e.g., telegram, twilio, openai) |
| attempt_count | int | No | Number of attempts made |
| external_ref | text | No | External reference (e.g., Twilio message SID) |
| error_message | text | No | Error message if action failed |
| created_at | timestamptz | Yes | Action creation timestamp |

---

### 6.5 🧾 Operator Actions Table (`public.operator_actions`)

Generic operator action log for each case.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | uuid | Yes | Auto-generated primary key |
| case_id | uuid | Yes | Foreign key to alerts(id) |
| operator | text | Yes | Operator label/id (for hackathon default: Operator 1) |
| actions_taken | text | Yes | Generic action key (e.g. dispatch_ambulance, call_family, mark_attended, incident_note) |
| action_payload | jsonb | No | Flexible structured metadata (e.g., contacted family member IDs/names, notes) |
| action_time | timestamptz | Yes | Time action occurred (defaults to now) |
| created_at | timestamptz | Yes | Row creation timestamp |

---

### 6.6 💬 Senior Conversations Table (`public.senior_conversations`)

Tracks follow-up conversation windows opened after AI decisions.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | uuid | Yes | Auto-generated primary key |
| senior_id | uuid | Yes | Foreign key to seniors(id) |
| alert_id | uuid | Yes | Foreign key to alerts(id) |
| status | text | Yes | active/completed/timeout |
| senior_response | text | No | Final normalized senior response text |
| started_at | timestamptz | Yes | Conversation start time |
| ended_at | timestamptz | No | Conversation completion/timeout time |
| updated_at | timestamptz | Yes | Auto-updated timestamp |
| created_at | timestamptz | Yes | Row creation timestamp |

---

### 6.7 🔐 Security Model

  * Seniors have no direct DB access
  * Backend uses Supabase service role
  * Operators authenticate via Supabase Auth
  * Row Level Security enabled
  * Public access blocked
  * `public.operator_actions` protected by RLS with service-role full access and authenticated read policy

---

## 7. 🔐 Security & Governance

* Hackathon-grade secure:

  * No public database access
  * No client-side service keys
  * Operator login required
  * Audit trail for all AI + operator actions

* AI never auto-dispatches emergency services.

* Human-in-the-loop design is enforced.

---

## 8. 🧪 Example Scenarios

### 🟢 Accidental Press (FALSE_ALARM)

* Transcript:

  * "Sorry I pressed wrongly."

* AI:

  * FALSE_ALARM risk (0.12)
  * Senior receives apology + "Escalate" button
  * No family notification by default
  * If senior clicks button → escalate to NON_URGENT and notify family

### 🟡 Unclear Distress (UNCERTAIN)

* Transcript:

  * "I feel a bit dizzy but I'm okay."

* AI:

  * UNCERTAIN risk (0.45)
  * Senior receives "I am okay" + "Escalate" buttons
  * Contacts flagged with `notify_on_uncertain` may be notified
  * If senior clicks escalate → move to NON_URGENT and notify family

### 🟠 Follow-up Needed (NON_URGENT)

* Transcript:

  * "I feel weak and need someone to check on me soon."

* AI:

  * NON_URGENT risk (0.68)
  * Family is notified
  * Case is escalated to operations as NON_URGENT
  * Operator follows up shortly

### 🔴 Fall Incident (URGENT)

* Transcript:

  * "I fell and cannot stand up."

* AI:

  * URGENT risk (0.94)
  * Escalates immediately
  * Displays address & medical history
  * Suggests ambulance dispatch
  * Senior receives confirmation (no button - already escalated)

* Operator confirms action.

---

## 9. 🏆 Hackathon Positioning

* PersonalAlertPlus is positioned as:

  * An AI-assisted triage extension that enhances GovTech’s Personal Alert Button ecosystem through intelligent digital accessibility and operator support.

* We extend infrastructure.

* We do not replace it.

---

## 10. 🔮 Future Enhancements

* WhatsApp integration
* Dialect fine-tuned speech models
* Real-time analytics via ClickHouse
* Risk trend heatmaps
* AI retraining from operator feedback
* Integration with emergency dispatch APIs
* SMS fallback channel (implemented)
* Caregiver mobile app
* Twilio call-response webhook handling for check-in keypad responses
* Multi-language operator dashboard

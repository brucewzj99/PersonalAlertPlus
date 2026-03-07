# PersonalAlertPlus - System Flowchart

## High-Level Architecture

```mermaid
flowchart TB
    subgraph Telegram["Telegram Layer (app/bot/)"]
        T1[Senior sends text or voice]
        T2[Registration + profile handlers]
        T3[Alert handlers]
        T4[Escalate/confirm/skip callbacks]
        T5[Conversation reply handler]
    end

    subgraph API["FastAPI Layer (app/)"]
        A1[POST /telegram/webhook]
        A2[GET /health]
        A3[POST /api/v1/brain/alerts/ingest]
        A4[GET /api/v1/brain/health]
        A5[POST /api/v1/brain/conversations/check-timeout]
        A6[Operator API routes]
    end

    subgraph Brain["Brain Layer (app/brain/)"]
        B1[router.py]
        B2[orchestrator.py]
        B3[speech_to_text.py]
        B4[risk_engine.py]
        B5[notification_service.py]
        B6[action_logger.py]
        B7[conversation_timeout.py]
        B8[twilio_call_service.py]
    end

    subgraph Dashboard["Operator Dashboard (dashboard/src/App.tsx)"]
        O1[Alerts queue + case modal]
        O2[Override + action logging]
        O3[Few-shot example manager]
        O4[Prompt settings manager]
        O5[Seniors + emergency contacts manager]
        O6[Conversation replies view]
    end

    subgraph DB["Supabase (Postgres + Storage)"]
        D1[(seniors)]
        D2[(emergency_contacts)]
        D3[(alerts)]
        D4[(ai_actions)]
        D5[(operator_actions)]
        D6[(few_shot_examples)]
        D7[(senior_conversations)]
        D8[(prompt_settings)]
        D9[(alerts-audio storage)]
    end

    subgraph External["External Services"]
        E1[Telegram API]
        E2[OpenAI-compatible AI API]
        E3[Twilio SMS]
        E4[Twilio Voice Call]
    end

    T1 --> T3
    T1 --> T5
    T3 --> A3
    T4 --> B2
    T5 --> D7
    T5 --> D4
    T5 --> D3

    A1 --> T2
    A1 --> T3
    A1 --> T4
    A2 --> B1
    A3 --> B1
    A4 --> B1
    A5 --> B7
    A6 --> O1

    B1 --> B2
    B2 --> B3
    B2 --> B4
    B2 --> B5
    B2 --> B6
    B7 --> B8

    B3 --> E2
    B4 --> E2
    B5 --> E1
    B5 --> E3
    B8 --> E4

    B2 --> D1
    B2 --> D2
    B2 --> D3
    B2 --> D4
    B2 --> D7
    B3 --> D9
    O2 --> D3
    O2 --> D5
    O3 --> D6
    O4 --> D8
    O5 --> D1
    O5 --> D2
    O6 --> D4
```

---

## End-to-End Data Flow

```mermaid
sequenceDiagram
    participant Senior
    participant Bot as Telegram Bot
    participant API as FastAPI
    participant Brain as Brain Orchestrator
    participant AI as OpenAI-Compatible API
    participant DB as Supabase
    participant Notify as Telegram/Twilio
    participant Ops as Operator Dashboard

    Note over Senior,DB: 1) Trigger + ingest
    Senior->>Bot: Send voice/text alert
    Bot->>DB: Insert alerts row (pending)
    Bot->>API: POST /api/v1/brain/alerts/ingest
    API->>Brain: process_alert(payload)

    Note over Brain,AI: 2) AI processing
    Brain->>DB: Load senior + emergency contacts
    Brain->>AI: STT + language detect (voice path)
    Brain->>AI: Translate to English when needed
    Brain->>AI: Risk classification
    Brain->>Brain: Apply guardrails (keywords + translation quality)
    Brain->>DB: Update alerts (risk, score, ai_assessment, status)
    Brain->>DB: Log ai_actions

    Note over Brain,Notify: 3) Notifications by risk
    alt URGENT or NON_URGENT
        Brain->>Notify: Notify contacts (Telegram then SMS fallback)
        Brain->>DB: Create senior_conversations(status=active)
        Brain->>Senior: Send follow-up "need info" audio + Skip button
    else UNCERTAIN
        Brain->>Notify: Notify only contacts with notify_on_uncertain=true
        Brain->>DB: Create senior_conversations(status=active)
        Brain->>Senior: Send "I am okay" / "Escalate" buttons
    else FALSE_ALARM
        Brain->>Senior: Send Escalate button only
    end

    Note over Senior,DB: 4) Senior callback/reply paths
    opt Senior taps Escalate
        Senior->>Bot: callback escalate_non_urgent:{alert_id}
        Bot->>DB: Update alert to NON_URGENT + escalated
        Bot->>Notify: Notify contacts as escalation
        Bot->>DB: Log ai_actions (senior_escalated_to_non_urgent)
    end

    opt Senior sends follow-up text/voice
        Senior->>Bot: follow-up reply
        Bot->>DB: Complete senior_conversations row
        Bot->>DB: Log ai_actions (senior_conversation_reply)
        Bot->>DB: Update alerts.senior_response + requires_operator=true
    end

    Note over API,DB: 5) Timeout safety net
    API->>Brain: periodic timeout check (every 5s scheduler)
    Brain->>DB: Find active senior_conversations past timeout
    alt timed-out alert is UNCERTAIN
        Brain->>Notify: Twilio check-in voice call
        Brain->>DB: Log ai_actions (conversation_timeout, checkin_call)
    else timed-out alert is other risk
        Brain->>DB: Mark timeout only
    end

    Note over Ops,DB: 6) Operator handling
    Ops->>API: PATCH /api/v1/operator/alerts/{id}/override
    API->>DB: Update alert + insert operator_actions rows
    API->>Senior: Optional multilingual operator action update (voice/text)
```

---

## Database Schema Flow

```mermaid
erDiagram
    SENIORS ||--o{ ALERTS : has_many
    SENIORS ||--o{ EMERGENCY_CONTACTS : has_many
    ALERTS ||--o{ AI_ACTIONS : has_many
    ALERTS ||--o{ OPERATOR_ACTIONS : has_many
    ALERTS ||--o{ SENIOR_CONVERSATIONS : has_many

    SENIORS {
        uuid id PK
        text full_name
        text phone_number UK
        text telegram_user_id
        text address
        int birth_year
        int birth_month
        int birth_day
        text preferred_language
        text medical_notes
        timestamptz created_at
    }

    EMERGENCY_CONTACTS {
        uuid id PK
        uuid senior_id FK
        text name
        text relationship
        text phone_number
        text telegram_user_id
        int priority_order
        bool notify_on_uncertain
        timestamptz created_at
    }

    ALERTS {
        uuid id PK
        uuid senior_id FK
        text channel
        text audio_url
        text transcription
        text translated_text
        text language_detected
        text risk_level
        numeric risk_score
        text ai_assessment
        text analysis_summary
        jsonb keywords
        text status
        bool requires_operator
        bool is_resolved
        text resolved_by
        text senior_response
        text processing_status
        text processing_error
        timestamptz created_at
    }

    AI_ACTIONS {
        uuid id PK
        uuid alert_id FK
        text action_type
        text action_status
        jsonb details
        text provider
        int attempt_count
        text external_ref
        text error_message
        timestamptz created_at
    }

    OPERATOR_ACTIONS {
        uuid id PK
        uuid case_id FK
        text operator
        text actions_taken
        jsonb action_payload
        timestamptz action_time
        timestamptz created_at
    }

    SENIOR_CONVERSATIONS {
        uuid id PK
        uuid senior_id FK
        uuid alert_id FK
        text status
        text senior_response
        timestamptz started_at
        timestamptz ended_at
        timestamptz updated_at
        timestamptz created_at
    }

    FEW_SHOT_EXAMPLES {
        uuid id PK
        text transcript
        text risk_level
        timestamptz created_at
    }

    PROMPT_SETTINGS {
        text key PK
        text value
        text description
        timestamptz updated_at
        timestamptz created_at
    }
```

---

## Quick Reference: API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Basic service health check |
| `/telegram/webhook` | POST | Telegram update ingress (webhook mode) |
| `/api/v1/brain/alerts/ingest` | POST | Brain processing entrypoint |
| `/api/v1/brain/health` | GET | Brain health check |
| `/api/v1/brain/conversations/check-timeout` | POST | Manual timeout check trigger |
| `/api/v1/operator/alerts` | GET | Operator alert feed |
| `/api/v1/operator/alerts/{alert_id}/override` | PATCH | Override alert + persist operator action rows |
| `/api/v1/operator/alerts/{alert_id}/conversation-replies` | GET | Fetch recent senior follow-up replies |
| `/api/v1/operator/few-shot-examples` | GET | List few-shot examples |
| `/api/v1/operator/few-shot-examples` | POST | Create few-shot example |
| `/api/v1/operator/few-shot-examples/{example_id}` | PATCH | Update few-shot example |
| `/api/v1/operator/few-shot-examples/{example_id}` | DELETE | Delete few-shot example |
| `/api/v1/operator/seniors/overview` | GET | Senior overview for dashboard |
| `/api/v1/operator/seniors/{senior_id}/emergency-contacts` | GET | List contacts for one senior |
| `/api/v1/operator/seniors/{senior_id}/emergency-contacts` | POST | Create contact for one senior |
| `/api/v1/operator/emergency-contacts/{contact_id}` | PATCH | Update one emergency contact |
| `/api/v1/operator/emergency-contacts/{contact_id}` | DELETE | Delete one emergency contact |
| `/api/v1/operator/settings/risk-prompt` | GET/PUT | Read or update base risk prompt |

---

## Notes

- Timeout checking is run automatically by `apscheduler` in `app/main.py` every 5 seconds.
- `TwilioCallService` generates TwiML with gather action `/api/v1/twilio/gather`; that callback route is not implemented in this codebase yet.
- Operator action state is derived from `operator_actions` rows in the API layer and shown in the dashboard.

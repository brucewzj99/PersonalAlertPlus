# PersonalAlertPlus - System Flowchart

## High-Level Architecture

```mermaid
flowchart TB
    subgraph Telegram["🤖 Telegram Layer (app/bot/)"]
        TB1[User sends Voice/Text]
        TB2[Webhook/Polling Handler]
        TB3[Registration Flow]
        TB4[Profile Management]
        TB5[Alert Handler]
    end

    subgraph API["🌐 FastAPI Layer (app/)"]
        API1["POST /telegram/webhook"]
        API2["POST /api/v1/brain/alerts/ingest"]
        API3["GET /api/v1/brain/health"]
        API4["GET /health"]
    end

    subgraph Brain["🧠 Brain Layer (app/brain/)"]
        B1[Router<br/>app/brain/router.py]
        B2[Orchestrator<br/>app/brain/orchestrator.py]
        
        subgraph Providers["AI Providers (app/brain/providers/)"]
            P1[OpenAI-Compatible Client<br/>openai_compatible.py]
            P2[Whisper STT]
            P3[Chat LLM]
        end
        
        subgraph Services["Brain Services (app/brain/services/)"]
            S1[Audio Fetcher<br/>audio_fetcher.py]
            S2[Risk Engine<br/>risk_engine.py]
            S3[Notification Service<br/>notification_service.py]
            S4[Action Logger<br/>action_logger.py]
        end
        
        subgraph Prompts["Prompts (app/brain/prompts.py)"]
            PM1[Translation Prompts]
            PM2[Classification Prompts]
            PM3[Keyword Detection]
        end
    end

    subgraph Bot_Handlers["🤖 Bot Handlers (app/bot/handlers/)"]
        BH1[Escalate Handler<br/>escalate.py]
    end

    subgraph DB["🗄️ Database Layer (Supabase)"]
        DB1[(Seniors)]
        DB2[(Emergency Contacts)]
        DB3[(Alerts)]
        DB4[(AI Actions)]
    end

    subgraph External["🔌 External Services"]
        E1[OpenAI API]
        E2[Whisper API]
        E3[Telegram API]
        E4[Twilio SMS]
    end

    TB1 --> TB2
    TB2 --> API1
    API1 --> TB3
    API1 --> TB4
    API1 --> TB5
    
    TB5 -->|"POST /api/v1/brain/alerts/ingest"| API2
    API2 --> B1
    
    B1 --> B2
    B2 --> S1
    S1 -->|"Fetch Audio"| DB3
    DB3 -->|"Audio URL"| S1
    
    S1 -->|"Audio Bytes"| B2
    B2 --> P1
    P1 -->|"Audio"| P2
    P2 -->|"Transcript"| P1
    
    P1 -->|"Translate"| PM1
    PM1 -->|"English Text"| P1
    
    P1 -->|"Classify"| P3
    P3 --> PM2
    PM2 -->|"Risk Level"| P1
    
    P1 -->|"Analysis"| B2
    B2 --> S2
    S2 --> PM3
    PM3 -->|"Guardrails"| S2
    S2 -->|"Final Risk"| B2
    
    B2 -->|"Update Alert"| DB3
    B2 -->|"Log Action"| DB4
    
    B2 --> S3
    S3 -->|"Notify Family"| E3
    S3 -->|"SMS Fallback"| E4
    
    B2 -->|"Senior Confirmation"| E3
    E3 -->|"Inline Button (UNCERTAIN/FALSE_ALARM)"| BH1
    
    BH1 -->|"Click 'Escalate'"| B2
    BH1 -->|"Click 'I am okay'"| B2
    BH1 -->|"Escalate"| E3
    BH1 -->|"Notify Family Again"| E4
    
    B2 -->|"Get Senior"| DB1
    B2 -->|"Get Contacts"| DB2
```

---

## Data Flow Diagram

```mermaid
sequenceDiagram
    participant User as Senior/User
    participant TB as Telegram Bot
    participant API as FastAPI
    participant Brain as Brain Orchestrator
    participant AI as OpenAI API
    participant DB as Supabase
    participant Notif as Telegram/Twilio

    Note over User,DB: Step 1: User Registration Flow
    User->>TB: /start command
    TB->>API: Telegram Update
    API->>TB: Request language selection
    User->>TB: Select language
    TB->>TB: Collect name, phone, address, birthday
    TB->>DB: Insert senior record
    DB-->>TB: Senior created
    TB->>User: Registration complete ✓

    Note over User,DB: Step 2: Alert Triggered
    User->>TB: Send Voice Message
    TB->>API: Telegram Update (VOICE)
    API->>TB: Download voice file
    TB->>DB: Upload to Storage bucket
    DB-->>TB: audio_url returned
    TB->>DB: Insert alert record
    DB-->>TB: alert_id returned
    TB->>API: POST /api/v1/brain/alerts/ingest<br/>{senior_id, audio_url, ...}
    API->>Brain: Process alert

    Note over Brain,DB: Step 3: AI Processing
    Brain->>DB: Get senior details
    DB-->>Brain: {name, address, medical_notes}
    Brain->>DB: Get emergency contacts
    DB-->>Brain: [{name, telegram_id, phone}]
    Brain->>DB: Fetch audio from URL
    DB-->>Brain: audio_bytes
    
    Brain->>AI: Whisper API (transcribe)
    AI-->>Brain: "I fell down and cannot get up"
    
    Brain->>AI: Translate to English (if needed)
    AI-->>Brain: English transcript
    
    Brain->>AI: Classify risk (GPT)
    AI-->>Brain: {risk_level: URGENT, score: 0.94, reasoning: ...}
    
    Brain->>Brain: Apply guardrails
    Brain->>DB: Update alert with analysis
    DB-->>Brain: Alert updated ✓

    Note over Brain,Notif: Step 4: Notification
    Brain->>Notif: Send Telegram to emergency contact
    Notif-->>Brain: Message sent ✓
    Brain->>DB: Log notification action
```

---

## Database Schema Flow

```mermaid
erDiagram
    SENIORS ||--o{ ALERTS : "has many"
    SENIORS ||--o{ EMERGENCY_CONTACTS : "has many"
    ALERTS ||--o{ AI_ACTIONS : "has many"
    ALERTS ||--o{ OPERATOR_ACTIONS : "has many"

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
        text language_detected
        text risk_level
        numeric risk_score
        text status
        bool requires_operator
        text resolved_by
        text processing_status
        text processing_error
        text translated_text
        text analysis_summary
        jsonb keywords
        jsonb provider_metadata
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
        uuid alert_id FK
        uuid operator_id FK
        text ai_recommendation
        text operator_decision
        text decision_notes
        int ai_accuracy_rating
        bool overridden
        timestamptz created_at
    }
```

---

## Case Examples

### Case 1: FALSE_ALARM (Accidental Trigger)

```mermaid
sequenceDiagram
    participant Senior
    participant Bot
    participant Brain
    participant AI

    Senior->>Bot: "Sorry, I pressed wrongly"
    Bot->>Brain: POST /alerts/ingest
    Brain->>AI: Classify risk
    AI-->>Brain: {risk_level: FALSE_ALARM, score: 0.12}
    Brain->>Database: Update alert (FALSE_ALARM, closed)
    Brain->>Senior: Apology + "Escalate" button
```

**Flow Summary:**
1. Alert is classified as `FALSE_ALARM`.
2. System closes the case and does not notify family by default.
3. Senior can still click "Escalate" to move into the NON_URGENT flow.

---

### Case 2: UNCERTAIN (Needs Confirmation)

```mermaid
sequenceDiagram
    participant Senior
    participant Bot
    participant Brain
    participant AI

    Senior->>Bot: "I feel strange... not sure"
    Bot->>Brain: POST /alerts/ingest
    Brain->>AI: Classify risk
    AI-->>Brain: {risk_level: UNCERTAIN, score: 0.47}
    Brain->>Database: Update alert (UNCERTAIN, pending_confirmation)
    Brain->>Senior: Bilingual reply + "I am okay" and "Escalate"
```

**Flow Summary:**
1. Alert is classified as `UNCERTAIN`.
2. System asks senior to confirm status via inline buttons.
3. Family is not notified unless senior escalates.

---

### Case 3: NON_URGENT (Follow-Up Required)

```mermaid
sequenceDiagram
    participant Senior
    participant Bot
    participant Brain
    participant AI
    participant Family
    participant Operator

    Senior->>Bot: "Please check on me soon, feeling weak"
    Bot->>Brain: POST /alerts/ingest
    Brain->>AI: Classify risk
    AI-->>Brain: {risk_level: NON_URGENT, score: 0.68}
    Brain->>Database: Update alert (NON_URGENT, escalated)
    Brain->>Family: Notify family contacts
    Brain->>Operator: Escalate as NON_URGENT
```

**Flow Summary:**
1. Alert is classified as `NON_URGENT`.
2. Family is notified.
3. Case is escalated to operations as NON_URGENT.

---

### Case 4: URGENT (Immediate Emergency)

```mermaid
sequenceDiagram
    participant Senior
    participant Bot
    participant Brain
    participant AI
    participant Family
    participant Operator

    Senior->>Bot: "I fell down, cannot get up"
    Bot->>Brain: POST /alerts/ingest
    Brain->>AI: Classify risk
    AI-->>Brain: {risk_level: URGENT, score: 0.92}
    Brain->>Database: Update alert (URGENT, escalated)
    Brain->>Family: Notify family contacts immediately
    Brain->>Operator: Escalate as URGENT priority
```

**Flow Summary:**
1. Alert is classified as `URGENT`.
2. Family is notified immediately.
3. Case is escalated to operations with URGENT priority.

---

### Case 5: Senior Escalation (from UNCERTAIN/FALSE_ALARM)

```mermaid
sequenceDiagram
    participant Senior
    participant Bot
    participant Brain
    participant Family

    Brain->>Senior: UNCERTAIN/FALSE_ALARM follow-up<br/>+ "Escalate" button
    Senior->>Bot: Click "Escalate"
    Bot->>Brain: Callback: escalate_non_urgent:{alert_id}
    Brain->>Database: Update alert to NON_URGENT<br/>status=escalated
    Brain->>Database: Log senior_escalated_to_non_urgent action
    Brain->>Family: Send "SENIOR ESCALATED" notification
    Brain->>Senior: "Your alert has been escalated"
```

**Flow Summary:**
1. Senior received UNCERTAIN/FALSE_ALARM follow-up with "Escalate" button.
2. Bot handler processes callback `escalate_non_urgent:{alert_id}`.
3. Alert is upgraded to NON_URGENT and marked for operator review.
4. Family is notified and senior receives escalation confirmation.

---

## Folder Structure Summary

| Folder/File | Purpose |
|-------------|---------|
| `app/bot/` | Telegram bot handlers, conversations, keyboards |
| `app/bot/handlers/alerts.py` | Handle voice/text alerts |
| `app/bot/handlers/profile.py` | Profile management commands |
| `app/bot/handlers/escalate.py` | Confirm/Escalate callback handler |
| `app/bot/conversations/registration.py` | Registration flow |
| `app/brain/router.py` | FastAPI endpoints (`/api/v1/brain/*`) |
| `app/brain/orchestrator.py` | Main processing pipeline |
| `app/brain/providers/openai_compatible.py` | OpenAI/Whisper API client |
| `app/brain/services/audio_fetcher.py` | Download audio from Supabase |
| `app/brain/services/risk_engine.py` | Classification guardrails |
| `app/brain/services/notification_service.py` | Telegram/Twilio notifications |
| `app/brain/services/action_logger.py` | Log to `ai_actions` table |
| `app/brain/prompts.py` | LLM prompts & keyword detection |
| `app/services/database.py` | Supabase client wrapper |
| `app/services/storage.py` | Supabase Storage upload |
| `app/config.py` | Configuration & env variables |
| `app/main.py` | FastAPI app entry point |

---

## Quick Reference: API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Basic health check |
| `/telegram/webhook` | POST | Telegram bot updates |
| `/api/v1/brain/alerts/ingest` | POST | Process new alert |
| `/api/v1/brain/health` | GET | Brain service health |

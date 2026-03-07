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
    E3 -->|"Inline Button (LOW/MEDIUM)"| BH1
    
    BH1 -->|"Click 'I'm not okay'"| B2
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
    AI-->>Brain: {risk_level: HIGH, score: 0.94, reasoning: ...}
    
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

### Case 1: Accidental Press (LOW Risk)

```mermaid
sequenceDiagram
    participant Senior
    participant Bot
    participant Brain
    participant AI
    participant Family

    Senior->>Bot: Voice: "Sorry, I pressed wrongly"
    Bot->>Brain: POST /alerts/ingest
    Brain->>AI: Whisper transcription
    AI-->>Brain: "Sorry, I pressed wrongly"
    Brain->>AI: Risk classification
    AI-->>Brain: {risk_level: LOW, score: 0.12}
    Brain->>Brain: Guardrails check (no emergency keywords)
    Brain->>Database: Update alert (LOW, 0.12)
    Brain->>Family: Telegram notification
    Family-->>Senior: Acknowledge
    Brain->>Database: Log action, close alert
    Brain->>Senior: Send confirmation message<br/>+ "I'm not okay" button
```

**Flow Summary:**
1. Senior sends voice message accidentally
2. Bot uploads to Supabase → calls brain endpoint
3. Whisper transcribes → "Sorry, I pressed wrongly"
4. LLM classifies as **LOW risk** (0.12 confidence)
5. Guardrails confirm no emergency keywords
6. Alert saved with `risk_level=LOW`, `status=closed`
7. Family notified via Telegram
8. **Senior receives confirmation message with "I'm not okay" button**
9. If senior clicks button → escalate to HIGH

---

### Case 2: Fall Incident (HIGH Risk)

```mermaid
sequenceDiagram
    participant Senior
    participant Bot
    participant Brain
    participant AI
    participant Family
    participant Operator

    Senior->>Bot: Voice: "I fell down, cannot get up"
    Bot->>Brain: POST /alerts/ingest
    Brain->>AI: Whisper transcription
    AI-->>Brain: "I fell down, cannot get up"
    Brain->>AI: Risk classification
    AI-->>Brain: {risk_level: HIGH, score: 0.89}
    Brain->>Brain: Guardrails check (keyword: "fell")
    Brain->>Database: Update alert (HIGH, 0.94, escalated)
    Brain->>Family: Telegram + SMS notification
    Brain->>Database: Log HIGH-risk notification
    Brain->>Senior: Send confirmation message<br/>(no button - already escalated)
    Note over Operator: Dashboard sees alert
    Operator->>Database: Review alert, dispatch ambulance
    Operator->>Database: Log operator action
```

**Flow Summary:**
1. Senior sends voice: "I fell down, cannot get up"
2. Bot uploads → calls brain endpoint
3. Whisper transcribes → "I fell down, cannot get up"
4. LLM classifies as **HIGH risk** (0.89)
5. Guardrails elevate due to "fell" keyword → 0.94
6. Alert saved with `risk_level=HIGH`, `status=escalated`, `requires_operator=true`
7. Family notified immediately via Telegram + SMS
8. **Senior receives confirmation message (no inline button - already escalated)**
9. Operator sees alert on dashboard, takes action

---

### Case 3: Non-English Voice (Chinese)

```mermaid
sequenceDiagram
    participant Senior
    participant Bot
    participant Brain
    participant AI

    Senior->>Bot: Voice (Hokkien): "我跌倒了"
    Bot->>Brain: POST /alerts/ingest
    Brain->>AI: Whisper transcription (detects: Chinese)
    AI-->>Brain: "wo die dao le" (pinyin approximation)
    Brain->>AI: Translate to English
    AI-->>Brain: "I fell down"
    Brain->>AI: Risk classification (English text)
    AI-->>Brain: {risk_level: HIGH, score: 0.91}
    Brain->>Database: Update alert with<br/>transcription, translated_text, analysis
```

**Flow Summary:**
1. Senior sends voice in Hokkien
2. Whisper detects Chinese language
3. Transcription: "wo die dao le" (phonetic)
4. Translation prompt converts to English: "I fall down"
5. Classification runs on English text → HIGH risk
6. Database stores both original + translated text
7. Analysis summary generated for operator

---

### Case 4: Text Alert (No Voice)

```mermaid
sequenceDiagram
    participant Senior
    participant Bot
    participant Brain
    participant AI

    Senior->>Bot: Text: "I need help, chest pain"
    Bot->>Brain: POST /alerts/ingest<br/>{text: "I need help, chest pain"}
    Brain->>Brain: Skip audio fetch
    Brain->>AI: Risk classification (text directly)
    AI-->>Brain: {risk_level: HIGH, score: 0.96}
    Brain->>Brain: Guardrails (keyword: "chest pain")
    Brain->>Database: Update alert
    Brain->>Family: Emergency notification
```

**Flow Summary:**
1. Senior sends text message instead of voice
2. Bot calls brain endpoint with `text` field (no `audio_url`)
3. Brain skips audio fetch step
4. Classification runs directly on text
5. Guardrails elevate due to "chest pain" keyword
6. HIGH risk alert → immediate escalation
7. **Senior receives confirmation message with inline button**

---

### Case 5: Senior Escalation ("I'm not okay" Button)

```mermaid
sequenceDiagram
    participant Senior
    participant Bot
    participant Brain
    participant Family

    Brain->>Senior: Confirmation message<br/>"Everything is fine"<br/>+ "I'm not okay" button
    Senior->>Bot: Click "I'm not okay"
    Bot->>Brain: Callback: escalate:{alert_id}
    Brain->>Database: Update alert to HIGH<br/>status=escalated
    Brain->>Database: Log senior_escalated action
    Brain->>Family: Send "SENIOR ESCALATED" notification
    Brain->>Senior: "Your alert has been escalated"
```

**Flow Summary:**
1. Senior received LOW/MEDIUM confirmation with "I'm not okay" button
2. Senior feels worse, clicks the button
3. Bot handler processes callback `escalate:{alert_id}`
4. Alert upgraded to HIGH risk, status=escalated
5. Emergency contacts notified again with "SENIOR ESCALATED" message
6. Senior receives confirmation that alert was escalated

---

## Folder Structure Summary

| Folder/File | Purpose |
|-------------|---------|
| `app/bot/` | Telegram bot handlers, conversations, keyboards |
| `app/bot/handlers/alerts.py` | Handle voice/text alerts |
| `app/bot/handlers/profile.py` | Profile management commands |
| `app/bot/handlers/escalate.py` | "I'm not okay" callback handler |
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

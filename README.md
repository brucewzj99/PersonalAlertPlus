# PersonalAlertPlus Telegram Bot

Telegram bot service for senior registration and alert ingestion, built with `python-telegram-bot v22` + `FastAPI` + `Supabase`.

## What it does

- `/start` launches registration for new users.
- Registration asks fields in sequence with language selected first.
- Required fields: preferred language, name, phone number, address, birth year/month/day.
- Optional field: medical notes (with inline `Skip` button).
- After registration, users can send text or voice alerts.
- Voice files are uploaded to Supabase Storage.
- Bot inserts alert records into `alerts` and forwards payload to backend API.

## Language options

- English
- Chinese
- Malay
- Tamil
- Hokkien
- Cantonese

## Backend payload sent by bot

```json
{
  "senior_id": "uuid",
  "telegram_user_id": "123456789",
  "channel": "telegram",
  "audio_url": "https://...",
  "text": null
}
```

## Setup

1. Create virtual env and install dependencies:

```bash
pip install -r requirements.txt
```

2. Copy env file and fill values:

```bash
cp .env.example .env
```

3. Ensure Supabase Storage bucket exists and is publicly readable:

- Bucket name defaults to `alerts-audio`.

4. Choose bot mode in `.env`:

- Local default: `BOT_MODE=polling`
- Production: `BOT_MODE=webhook` and set `BOT_WEBHOOK_URL`

5. Run API server:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

or simply:

```bash
python main.py
```

## Telegram webhook

- Set `BOT_WEBHOOK_URL` to your public endpoint including path `/telegram/webhook`.
- Optional: set `BOT_WEBHOOK_SECRET` and configure same secret in Telegram webhook.
- Health endpoint: `GET /health`.

from functools import lru_cache
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    telegram_bot_token: str = Field(alias="TELEGRAM_BOT_TOKEN")
    supabase_url: str = Field(alias="SUPABASE_URL")
    supabase_secret_key: str = Field(alias="SUPABASE_SECRET_KEY")
    backend_api_url: str = Field(alias="BACKEND_API_URL")
    bot_mode: str = Field(default="polling", alias="BOT_MODE")

    bot_webhook_url: str | None = Field(default=None, alias="BOT_WEBHOOK_URL")
    bot_webhook_secret: str | None = Field(default=None, alias="BOT_WEBHOOK_SECRET")
    supabase_audio_bucket: str = Field(
        default="alerts-audio", alias="SUPABASE_AUDIO_BUCKET"
    )

    ai_api_base_url: str = Field(
        default="https://api.openai.com/v1", alias="AI_API_BASE_URL"
    )
    ai_api_base_url_stt: str = Field(
        default="https://api.openai.com/v1", alias="AI_API_BASE_URL_STT"
    )
    ai_api_key: str = Field(alias="AI_API_KEY")
    ai_api_key_stt: str | None = Field(
        default=None,
        alias="AI_API_KEY_STT",
        description="Optional key for STT/translation (e.g. Groq). If set, used for transcription/translation instead of AI_API_KEY.",
    )
    ai_chat_model: str = Field(default="gpt-4o-mini", alias="AI_CHAT_MODEL")

    @field_validator("ai_api_key", "ai_api_key_stt", mode="before")
    @classmethod
    def strip_api_key(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip() if isinstance(v, str) else v
    ai_transcription_model: str = Field(
        default="whisper-1", alias="AI_TRANSCRIPTION_MODEL"
    )
    ai_request_timeout_seconds: int = Field(
        default=30, alias="AI_REQUEST_TIMEOUT_SECONDS"
    )
    ai_max_retries: int = Field(default=3, alias="AI_MAX_RETRIES")
    ai_temperature: float = Field(default=0.1, alias="AI_TEMPERATURE")

    sms_provider: str = Field(default="twilio", alias="SMS_PROVIDER")
    twilio_account_sid: str | None = Field(default=None, alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str | None = Field(default=None, alias="TWILIO_AUTH_TOKEN")
    twilio_from_number: str | None = Field(default=None, alias="TWILIO_FROM_NUMBER")
    twilio_messaging_service_sid: str | None = Field(
        default=None, alias="TWILIO_MESSAGING_SERVICE_SID"
    )

    brain_processing_timeout_seconds: int = Field(
        default=45, alias="BRAIN_PROCESSING_TIMEOUT_SECONDS"
    )
    brain_enable_sms_fallback: bool = Field(
        default=True, alias="BRAIN_ENABLE_SMS_FALLBACK"
    )
    brain_notify_telegram_first: bool = Field(
        default=True, alias="BRAIN_NOTIFY_TELEGRAM_FIRST"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()

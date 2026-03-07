from __future__ import annotations

from typing import Any, cast

from supabase import Client, create_client
from postgrest.exceptions import APIError

from app.brain.prompts import DEFAULT_RISK_CLASSIFICATION_SYSTEM_PROMPT_TEMPLATE
from app.config import get_settings
from app.models.schemas import AlertInsert, Senior, FewShotExample, AlertUpdate


class DatabaseService:
    def __init__(self) -> None:
        settings = get_settings()
        self.client: Client = create_client(
            settings.supabase_url, settings.supabase_secret_key
        )
        self.default_risk_prompt_template = (
            DEFAULT_RISK_CLASSIFICATION_SYSTEM_PROMPT_TEMPLATE
        )

    def get_senior_by_telegram_user_id(self, telegram_user_id: str) -> Senior | None:
        response = (
            self.client.table("seniors")
            .select("*")
            .eq("telegram_user_id", telegram_user_id)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        if not rows:
            return None
        return Senior.model_validate(rows[0])

    def create_senior(self, payload: dict[str, Any]) -> Senior:
        response = self.client.table("seniors").insert(payload).execute()
        row = response.data[0]
        return Senior.model_validate(row)

    def create_alert(self, payload: AlertInsert) -> dict[str, Any]:
        response = self.client.table("alerts").insert(payload.model_dump()).execute()
        return self._as_dict_row((response.data or [None])[0])

    def update_senior(self, senior_id: str, updates: dict[str, Any]) -> Senior:
        response = (
            self.client.table("seniors")
            .update(updates)
            .eq("id", senior_id)
            .execute()
        )
        row = response.data[0]
        return Senior.model_validate(row)

    def get_few_shot_examples(self, limit: int = 5) -> list[FewShotExample]:
        try:
            response = (
                self.client.table("few_shot_examples")
                .select("*")
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
        except APIError:
            return []
        return [FewShotExample.model_validate(row) for row in (response.data or [])]

    def create_few_shot_example(self, example: FewShotExample) -> FewShotExample:
        response = (
            self.client.table("few_shot_examples")
            .insert(example.model_dump(exclude={"id", "created_at"}))
            .execute()
        )
        return FewShotExample.model_validate(response.data[0])

    def get_prompt_setting(self, key: str, default_value: str) -> str:
        try:
            response = (
                self.client.table("prompt_settings")
                .select("value")
                .eq("key", key)
                .limit(1)
                .execute()
            )
        except APIError:
            return default_value

        rows = response.data or []
        if not rows:
            return default_value
        first_row = self._as_dict_row(rows[0])
        value = first_row.get("value")
        if not isinstance(value, str):
            return default_value
        return value

    def set_prompt_setting(self, key: str, value: str) -> str:
        response = (
            self.client.table("prompt_settings")
            .upsert({"key": key, "value": value}, on_conflict="key")
            .execute()
        )
        rows = response.data or []
        if not rows:
            return value
        first_row = self._as_dict_row(rows[0])
        saved = first_row.get("value")
        return saved if isinstance(saved, str) else value

    def update_alert(self, alert_id: str, updates: AlertUpdate) -> dict[str, Any]:
        response = (
            self.client.table("alerts")
            .update(updates.model_dump(exclude_none=True))
            .eq("id", alert_id)
            .execute()
        )
        return self._as_dict_row((response.data or [None])[0])

    def _as_dict_row(self, row: Any) -> dict[str, Any]:
        if isinstance(row, dict):
            return cast(dict[str, Any], row)
        return {}

from __future__ import annotations

from typing import Any

from supabase import Client, create_client

from app.config import get_settings
from app.models.schemas import AlertInsert, Senior, FewShotExample, AlertUpdate


class DatabaseService:
    def __init__(self) -> None:
        settings = get_settings()
        self.client: Client = create_client(
            settings.supabase_url, settings.supabase_secret_key
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
        return response.data[0]

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
        response = (
            self.client.table("few_shot_examples")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return [FewShotExample.model_validate(row) for row in response.data]

    def create_few_shot_example(self, example: FewShotExample) -> FewShotExample:
        response = (
            self.client.table("few_shot_examples")
            .insert(example.model_dump(exclude={"id", "created_at"}))
            .execute()
        )
        return FewShotExample.model_validate(response.data[0])

    def update_alert(self, alert_id: str, updates: AlertUpdate) -> dict[str, Any]:
        response = (
            self.client.table("alerts")
            .update(updates.model_dump(exclude_none=True))
            .eq("id", alert_id)
            .execute()
        )
        return response.data[0]

from fastapi import APIRouter, HTTPException, Query
from app.services.database import DatabaseService
from app.models.schemas import AlertUpdate, FewShotExample
from typing import Any

router = APIRouter(prefix="/api/v1/operator", tags=["operator"])
db = DatabaseService()

@router.get("/alerts")
async def get_alerts(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
) -> list[dict[str, Any]]:
    """Fetch alerts sorted by priority (URGENT > NON_URGENT > UNCERTAIN > FALSE_ALARM) and time."""
    # Priority mapping for sorting
    # We can handle sorting in the application layer if Supabase doesn't support complex ordering easily
    try:
        response = (
            db.client.table("alerts")
            .select("*, seniors(full_name, phone_number, address)")
            .eq("is_resolved", False)
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
    except Exception as e:
        # Fallback if is_resolved column doesn't exist yet
        if "is_resolved" in str(e):
            response = (
                db.client.table("alerts")
                .select("*, seniors(full_name, phone_number, address)")
                .order("created_at", desc=True)
                .range(offset, offset + limit - 1)
                .execute()
            )
        else:
            raise e
    
    alerts = response.data or []
    
    # Custom sort: URGENT first, then NON_URGENT, then UNCERTAIN, then FALSE_ALARM.
    # Within each priority, newest alerts first.
    priority_order = {
        "URGENT": 4,
        "NON_URGENT": 3,
        "UNCERTAIN": 2,
        "FALSE_ALARM": 1,
        None: 0
    }
    
    sorted_alerts = sorted(
        alerts, 
        key=lambda x: (
            priority_order.get(x.get("risk_level")), 
            x.get("created_at") or ""
        ), 
        reverse=True
    )
    
    return sorted_alerts

@router.patch("/alerts/{alert_id}/override")
async def override_alert(
    alert_id: str,
    update: AlertUpdate,
    save_as_example: bool = Query(False)
) -> dict[str, Any]:
    """Override an alert's risk level and optionally save as a few-shot example."""
    # Fetch existing alert to get transcript
    response = db.client.table("alerts").select("transcription").eq("id", alert_id).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    transcript = response.data[0].get("transcription")
    
    # Update alert
    updated_alert = db.update_alert(alert_id, update)
    
    # Save as few-shot example if requested and risk_level is provided
    if save_as_example and transcript and update.risk_level:
        example = FewShotExample(
            transcript=transcript,
            risk_level=update.risk_level
        )
        db.create_few_shot_example(example)
        
    return updated_alert

@router.get("/few-shot-examples")
async def get_examples(limit: int = 10) -> list[FewShotExample]:
    """Fetch recent few-shot reinforcement examples."""
    return db.get_few_shot_examples(limit=limit)

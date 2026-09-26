from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from models import Setting
from services.discord import send_webhook
from services.digest import generate_digest, send_digest_to_discord
from services.ai_service import DEFAULT_MODELS

router = APIRouter(prefix="/api/digest", tags=["digest"])


async def _get_settings(db: AsyncSession) -> dict:
    result = await db.execute(select(Setting))
    return {s.key: s.value for s in result.scalars().all()}


@router.post("/test-webhook")
async def test_webhook(data: dict, db: AsyncSession = Depends(get_db)):
    webhook_url = data.get("webhook_url", "")
    if not webhook_url:
        raise HTTPException(400, "webhook_url required")

    success, err = await send_webhook(
        webhook_url,
        content="✅ **FeedWire** — webhook test successful. This webhook is correctly configured.",
    )
    if not success:
        raise HTTPException(502, f"Discord webhook test failed: {err}")
    return {"ok": True}


@router.post("/send-now")
async def send_digest_now(data: dict | None = None, db: AsyncSession = Depends(get_db)):
    """Manually trigger the digest send. Optional override webhook_url in body."""
    from database import SyncSession
    from services.digest import generate_digest as sync_generate

    settings = await _get_settings(db)
    override_webhook = (data or {}).get("webhook_url", "") if data else ""
    webhook = (
        override_webhook
        or settings.get("discord_digest_webhook_url", "")
        or settings.get("discord_webhook_url", "")
    )
    if not webhook:
        raise HTTPException(400, "No Discord webhook URL configured. Enter one in Settings and try again.")

    hours = int(settings.get("digest_hours") or "24")
    max_items = int(settings.get("digest_max_items_per_category") or "5")
    summarize = False  # Summarisation is disabled, including manual digests.

    provider = settings.get("ai_provider", "anthropic")
    api_key_map = {
        "anthropic": "anthropic_api_key",
        "openai": "openai_api_key",
        "openrouter": "openrouter_api_key",
        "gemini": "gemini_api_key",
        "ollama": "ollama_api_key",
    }
    api_key = settings.get(api_key_map.get(provider, ""), "")
    model = settings.get(f"{provider}_model", "") or DEFAULT_MODELS.get(provider, "")
    base_url = settings.get(f"{provider}_base_url", "")

    sync_session = SyncSession()
    try:
        digest = await sync_generate(
            sync_session,
            hours=hours,
            provider=provider,
            api_key=api_key,
            model=model,
            base_url=base_url,
            max_items_per_category=max_items,
            summarize_items=summarize,
        )
    finally:
        sync_session.close()

    if not digest:
        raise HTTPException(404, "No items in the time window")

    success, err = await send_digest_to_discord(digest, webhook, hours=hours)
    if not success:
        raise HTTPException(502, f"Failed to send to Discord: {err}")

    total = sum(len(items) for items in digest.values())
    return {"ok": True, "items": total, "categories": len(digest)}

import json
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from models import UsageLog, Setting
from services.usage import pricing_with_overrides

router = APIRouter(prefix="/api/ai", tags=["usage"])


class PricingUpdate(BaseModel):
    provider: str = Field(pattern="^(anthropic|openai|openrouter|gemini|ollama)$")
    model: str = Field(min_length=1, max_length=200, pattern=r"\S")
    input: Decimal = Field(ge=0, le=10000, allow_inf_nan=False)
    output: Decimal = Field(ge=0, le=10000, allow_inf_nan=False)
    cache_read: Decimal = Field(ge=0, le=10000, allow_inf_nan=False)
    cache_write: Decimal = Field(ge=0, le=10000, allow_inf_nan=False)


@router.get("/usage")
async def get_usage(days: int = Query(default=30, ge=1, le=365), db: AsyncSession = Depends(get_db)):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = await db.execute(
        select(UsageLog.provider, UsageLog.model,
               func.count().label("requests"),
               func.sum(UsageLog.input_tokens).label("input_tokens"),
               func.sum(UsageLog.output_tokens).label("output_tokens"),
               func.sum(UsageLog.cache_read_tokens).label("cache_read_tokens"),
               func.sum(UsageLog.cache_write_tokens).label("cache_write_tokens"),
               func.coalesce(func.sum(UsageLog.cost_usd), 0).label("known_cost_usd"),
               func.sum(case((UsageLog.status == "failed", 1), else_=0)).label("failed"),
               func.sum(case((UsageLog.cost_source == "estimated", 1), else_=0)).label("estimated"),
               func.sum(case(((UsageLog.cost_usd.is_(None)) & (UsageLog.status != "failed"), 1), else_=0)).label("unpriced"),
               func.sum(case(((UsageLog.usage_reported == False) & (UsageLog.status != "failed"), 1), else_=0)).label("missing_usage"))
        .where(UsageLog.created_at >= cutoff)
        .group_by(UsageLog.provider, UsageLog.model)
        .order_by(UsageLog.provider, UsageLog.model)
    )
    groups = [dict(row) for row in rows.mappings()]
    first = await db.scalar(select(func.min(UsageLog.created_at)))
    setting = await db.scalar(select(Setting).where(Setting.key == "ai_pricing"))
    return {"days": days, "tracking_since": first, "groups": groups,
            "requests": sum(g["requests"] for g in groups),
            "known_cost_usd": sum(g["known_cost_usd"] for g in groups),
            "unpriced": sum(g["unpriced"] for g in groups),
            "pricing": pricing_with_overrides(setting.value if setting else None)}


@router.patch("/pricing")
async def update_pricing(update: PricingUpdate, db: AsyncSession = Depends(get_db)):
    setting = await db.scalar(select(Setting).where(Setting.key == "ai_pricing").with_for_update())
    pricing = pricing_with_overrides(setting.value if setting else None)
    pricing[f"{update.provider}/{update.model.strip()}"] = {
        key: str(getattr(update, key)) for key in ("input", "output", "cache_read", "cache_write")
    }
    value = json.dumps(pricing)
    if setting:
        setting.value = value
    else:
        db.add(Setting(key="ai_pricing", value=value))
    await db.commit()
    return {"ok": True}

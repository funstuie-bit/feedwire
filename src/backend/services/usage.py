"""Provider metering. Records contain no keys, prompts, content or responses."""
import asyncio
import json
import logging
from decimal import Decimal, InvalidOperation
from sqlalchemy import select
from database import SyncSession
from models import Setting, UsageLog

logger = logging.getLogger(__name__)
# USD per million tokens, verified 2026-10-04 against Anthropic's pricing page.
# Unknown models stay unpriced until a rate is supplied; they never appear free.
DEFAULT_PRICING = {
    "anthropic/claude-haiku-4-5-20251001": {"input": 1, "output": 5, "cache_read": .1, "cache_write": 1.25},
    "anthropic/claude-haiku-4-5": {"input": 1, "output": 5, "cache_read": .1, "cache_write": 1.25},
    "anthropic/claude-sonnet-4-6": {"input": 3, "output": 15, "cache_read": .3, "cache_write": 3.75},
}


def pricing_with_overrides(value: str | None) -> dict:
    try:
        overrides = json.loads(value or "{}")
    except (ValueError, TypeError):
        overrides = {}
    return {**DEFAULT_PRICING, **(overrides if isinstance(overrides, dict) else {})}


def normalize_usage(provider: str, usage) -> dict:
    if hasattr(usage, "model_dump"):
        usage = usage.model_dump()
    if not isinstance(usage, dict):
        return {"usage_reported": False, "input_tokens": 0, "output_tokens": 0,
                "cache_read_tokens": 0, "cache_write_tokens": 0}
    def count(key):
        value = usage.get(key)
        return max(0, value) if isinstance(value, int) else 0
    if provider == "anthropic":
        cached, written = count("cache_read_input_tokens"), count("cache_creation_input_tokens")
        incoming, outgoing = count("input_tokens") + cached + written, count("output_tokens")
    elif provider == "gemini":
        cached, written = count("cached_content_token_count"), 0
        incoming = count("prompt_token_count")
        outgoing = count("candidates_token_count") + count("thoughts_token_count")
    else:
        details = usage.get("prompt_tokens_details") or {}
        cached = max(0, details.get("cached_tokens", 0) or 0) if isinstance(details, dict) else 0
        written = 0
        incoming, outgoing = count("prompt_tokens"), count("completion_tokens")
    token_keys = {"anthropic": ("input_tokens", "output_tokens"), "gemini": ("prompt_token_count", "candidates_token_count")}.get(provider, ("prompt_tokens", "completion_tokens"))
    reported = any(isinstance(usage.get(key), int) for key in token_keys)
    return {"usage_reported": reported, "input_tokens": incoming, "output_tokens": outgoing,
            "cache_read_tokens": cached, "cache_write_tokens": written}


def estimate_cost(provider: str, model: str, tokens: dict, pricing: dict, reported_cost=None):
    if reported_cost is not None:
        try:
            cost = Decimal(str(reported_cost))
            if cost.is_finite() and cost >= 0:
                return cost, "reported"
        except (InvalidOperation, ValueError):
            pass
    if provider == "ollama":
        return Decimal(0), "local"
    rate = pricing.get(f"{provider}/{model}")
    if not tokens["usage_reported"] or not isinstance(rate, dict):
        return None, "unknown"
    try:
        fresh = max(0, tokens["input_tokens"] - tokens["cache_read_tokens"] - tokens["cache_write_tokens"])
        cost = (Decimal(fresh) * Decimal(str(rate["input"]))
                + Decimal(tokens["output_tokens"]) * Decimal(str(rate["output"]))
                + Decimal(tokens["cache_read_tokens"]) * Decimal(str(rate["cache_read"]))
                + Decimal(tokens["cache_write_tokens"]) * Decimal(str(rate["cache_write"]))) / Decimal(1_000_000)
        return (cost, "estimated") if cost.is_finite() and cost >= 0 else (None, "unknown")
    except (KeyError, InvalidOperation, TypeError):
        return None, "unknown"


def _record(provider, model, usage, reported_cost, status):
    tokens = normalize_usage(provider, usage)
    with SyncSession() as db:
        setting = db.scalar(select(Setting).where(Setting.key == "ai_pricing"))
        pricing = pricing_with_overrides(setting.value if setting else None)
        cost, source = estimate_cost(provider, model, tokens, pricing, reported_cost)
        db.add(UsageLog(provider=provider, model=model, status=status, cost_usd=cost,
                        cost_source=source, **tokens))
        db.commit()


async def record_usage(provider, model, usage=None, reported_cost=None, status="success"):
    try:
        await asyncio.to_thread(_record, provider, model, usage, reported_cost, status)
    except Exception:
        # A metering failure must not discard a successfully billed model result.
        logger.warning("Could not save AI usage for %s/%s", provider, model, exc_info=True)

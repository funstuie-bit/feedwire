"""Meter provider fixtures without contacting AI services or a live database."""
import unittest
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock, patch
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from models import Base, UsageLog
from services.usage import normalize_usage, estimate_cost, DEFAULT_PRICING, _record
from services import ai_service
from routers.usage import get_usage, update_pricing, PricingUpdate


class AsyncDB:
    def __init__(self, db): self.db = db
    async def execute(self, query): return self.db.execute(query)
    async def scalar(self, query): return self.db.scalar(query)
    async def commit(self): self.db.commit()
    def add(self, value): self.db.add(value)


class UsageTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(self.engine)
        self.session_patch = patch("services.usage.SyncSession", self.sessions)
        self.session_patch.start()

    def tearDown(self):
        self.session_patch.stop()
        self.engine.dispose()

    def test_anthropic_cache_tokens_counted_once_and_priced_separately(self):
        tokens = normalize_usage("anthropic", {"input_tokens": 100, "output_tokens": 10, "cache_read_input_tokens": 50, "cache_creation_input_tokens": 20})
        self.assertEqual(tokens["input_tokens"], 170)
        cost, source = estimate_cost("anthropic", "claude-haiku-4-5-20251001", tokens, DEFAULT_PRICING)
        self.assertEqual((cost, source), (Decimal(".00018"), "estimated"))

    def test_missing_unknown_free_and_provider_reported_costs(self):
        tokens = normalize_usage("openrouter", {"prompt_tokens": 100, "completion_tokens": 10})
        self.assertEqual(estimate_cost("openrouter", "custom", tokens, {}, ".002"), (Decimal(".002"), "reported"))
        self.assertEqual(estimate_cost("openrouter", "custom", tokens, {}), (None, "unknown"))
        self.assertEqual(estimate_cost("ollama", "local", tokens, {}), (Decimal(0), "local"))
        for usage in [None, {}]:
            self.assertFalse(normalize_usage("anthropic", usage)["usage_reported"])
            self.assertEqual(estimate_cost("anthropic", "claude-haiku-4-5-20251001", normalize_usage("anthropic", usage), DEFAULT_PRICING), (None, "unknown"))

    def test_openai_cached_input_and_gemini_thinking(self):
        self.assertEqual(normalize_usage("openai", {"prompt_tokens": 100, "completion_tokens": 20, "prompt_tokens_details": {"cached_tokens": 40}})["input_tokens"], 100)
        tokens = normalize_usage("gemini", {"prompt_token_count": 100, "candidates_token_count": 20, "thoughts_token_count": 10, "cached_content_token_count": 40})
        self.assertEqual((tokens["input_tokens"], tokens["output_tokens"], tokens["cache_read_tokens"]), (100, 30, 40))

    async def test_actual_provider_helpers_record_successes(self):
        anthropic = AsyncMock()
        anthropic.messages.create.return_value = SimpleNamespace(model="claude-haiku-4-5-20251001", usage={"input_tokens": 100, "output_tokens": 10}, content=[SimpleNamespace(text="{}")])
        with patch("anthropic.AsyncAnthropic", return_value=anthropic):
            self.assertEqual(await ai_service._call_anthropic("private prompt", 10, "secret-key", "claude-haiku-4-5-20251001"), "{}")
        openai = AsyncMock()
        openai.chat.completions.create.return_value = SimpleNamespace(model="custom", usage=SimpleNamespace(model_dump=lambda: {"prompt_tokens": 50, "completion_tokens": 5, "cost": .001}), choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))])
        with patch("openai.AsyncOpenAI", return_value=openai):
            await ai_service._call_openai_compatible("private prompt", 10, "secret-key", "custom", "https://provider.example/v1", provider="openrouter")
        gemini = Mock()
        gemini.aio.models.generate_content = AsyncMock(return_value=SimpleNamespace(text="{}", usage_metadata={"prompt_token_count": 20, "candidates_token_count": 2}))
        with patch("google.genai.Client", return_value=gemini):
            await ai_service._call_gemini("private prompt", 10, "secret-key", "custom")
        with self.sessions() as db:
            rows = list(db.scalars(select(UsageLog).order_by(UsageLog.id)))
            self.assertEqual([row.provider for row in rows], ["anthropic", "openrouter", "gemini"])
            self.assertEqual([row.input_tokens for row in rows], [100, 50, 20])
            self.assertEqual(rows[1].cost_usd, Decimal(".001"))
            self.assertNotIn("private prompt", str([row.__dict__ for row in rows]))
            self.assertNotIn("secret-key", str([row.__dict__ for row in rows]))

    async def test_failure_record_and_aggregate_window(self):
        with patch.object(ai_service, "_call_llm", side_effect=RuntimeError("provider failed")):
            with self.assertRaises(RuntimeError):
                await ai_service.extract_entities("Title", "Text", api_key="test-only")
        _record("anthropic", "claude-haiku-4-5-20251001", {"input_tokens": 100, "output_tokens": 10}, None, "success")
        _record("openai", "custom", {"prompt_tokens": 10, "completion_tokens": 5}, None, "success")
        with self.sessions() as db:
            db.add(UsageLog(provider="old", model="old", created_at=datetime.now(timezone.utc) - timedelta(days=60)))
            db.commit()
            result = await get_usage(days=30, db=AsyncDB(db))
            self.assertEqual(result["requests"], 3)
            self.assertEqual(result["unpriced"], 1)
            self.assertEqual(sum(row["failed"] for row in result["groups"]), 1)
            self.assertEqual(result["known_cost_usd"], Decimal(".00015"))

    async def test_custom_rates_apply_only_to_future_requests(self):
        tokens = {"prompt_tokens": 100, "completion_tokens": 10}
        _record("openai", "custom", tokens, None, "success")
        with self.sessions() as db:
            await update_pricing(PricingUpdate(provider="openai", model="custom", input=1, output=5, cache_read=.1, cache_write=1), AsyncDB(db))
        _record("openai", "custom", tokens, None, "success")
        with self.sessions() as db:
            costs = list(db.scalars(select(UsageLog.cost_usd).order_by(UsageLog.id)))
            self.assertEqual(costs, [None, Decimal(".00015")])
        for price in [-1, "NaN", "Infinity"]:
            with self.assertRaises(ValidationError):
                PricingUpdate(provider="openai", model="custom", input=price, output=1, cache_read=1, cache_write=1)

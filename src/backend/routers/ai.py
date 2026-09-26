from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from models import Item, Setting
from schemas import AIRequest
from services.ai_service import extract_entities, DEFAULT_MODELS
from sqlalchemy import select

router = APIRouter(prefix="/api/ai", tags=["ai"])


async def _get_ai_config(db: AsyncSession) -> dict:
    result = await db.execute(select(Setting))
    settings = {s.key: s.value for s in result.scalars().all()}
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

    return {
        "provider": provider,
        "api_key": api_key,
        "model": model,
        "base_url": base_url,
    }


@router.post("/process")
async def process_item(request: AIRequest, db: AsyncSession = Depends(get_db)):
    if request.action == "summarize":
        raise HTTPException(410, "AI summarisation is disabled")
    item = await db.get(Item, request.item_id)
    if not item:
        raise HTTPException(404, "Item not found")

    config = await _get_ai_config(db)

    if request.action == "extract_entities":
        try:
            entities = await extract_entities(
                item.title or "", item.content or "",
                link=item.link or "",
                **config,
            )
            item.ai_entities = entities
            await db.commit()
            return {"entities": entities}
        except ValueError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            raise HTTPException(502, f"AI service error: {e}")

    else:
        raise HTTPException(400, f"Unknown action: {request.action}")


@router.post("/summarize-batch")
async def summarize_batch(
    item_ids: list[int], db: AsyncSession = Depends(get_db)
):
    raise HTTPException(410, "AI summarisation is disabled")


@router.get("/providers")
async def list_providers():
    """Return available providers and their default models."""
    return {
        "providers": [
            {
                "id": "anthropic",
                "name": "Anthropic (Claude)",
                "default_model": DEFAULT_MODELS["anthropic"],
                "needs_base_url": False,
                "model_examples": [
                    "claude-haiku-4-5-20251001",
                    "claude-sonnet-4-6",
                ],
            },
            {
                "id": "openai",
                "name": "OpenAI",
                "default_model": DEFAULT_MODELS["openai"],
                "needs_base_url": False,
                "model_examples": ["gpt-4o-mini", "gpt-4o"],
            },
            {
                "id": "openrouter",
                "name": "OpenRouter",
                "default_model": DEFAULT_MODELS["openrouter"],
                "needs_base_url": False,
                "model_examples": [
                    "google/gemini-2.0-flash-exp:free",
                    "meta-llama/llama-3.3-70b-instruct",
                    "deepseek/deepseek-chat",
                    "anthropic/claude-haiku-4-5",
                    "openai/gpt-4o-mini",
                    "qwen/qwen-2.5-72b-instruct",
                ],
            },
            {
                "id": "gemini",
                "name": "Google Gemini",
                "default_model": DEFAULT_MODELS["gemini"],
                "needs_base_url": False,
                "model_examples": [
                    "gemini-2.0-flash",
                    "gemini-2.0-flash-lite",
                    "gemini-1.5-pro",
                ],
            },
            {
                "id": "ollama",
                "name": "Ollama (Local)",
                "default_model": DEFAULT_MODELS["ollama"],
                "needs_base_url": True,
                "default_base_url": "http://host.docker.internal:11434/v1",
                "model_examples": [
                    "llama3.2",
                    "llama3.1",
                    "qwen2.5",
                    "mistral",
                    "phi3",
                ],
            },
        ],
    }

import os
import json
from typing import Optional
import httpx
from bs4 import BeautifulSoup
from services.usage import record_usage


def _strip_html(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    return soup.get_text(separator=" ", strip=True)


def _truncate(text: str, max_chars: int = 6000) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


def _content_is_thin(content: str, min_chars: int = 800) -> bool:
    """Check if content is too short to produce a good summary."""
    clean = _strip_html(content).strip()
    return len(clean) < min_chars


async def _fetch_article_content(url: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(
                url, headers={"User-Agent": "FeedWire/1.0 (RSS Reader)"}
            )
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")

        # Remove nav, header, footer, script, style, aside elements
        for tag in soup.find_all(["nav", "header", "footer", "script", "style", "aside", "form"]):
            tag.decompose()

        # Try common article selectors
        article = (
            soup.find("article")
            or soup.find(class_="post-content")
            or soup.find(class_="entry-content")
            or soup.find(class_="article-body")
            or soup.find(id="content")
            or soup.find("main")
        )

        if article:
            return article.get_text(separator=" ", strip=True)

        # Fallback: grab all paragraph text
        paragraphs = soup.find_all("p")
        text = " ".join(p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 40)
        return text or soup.get_text(separator=" ", strip=True)
    except Exception:
        return ""


async def _get_content(content: str, link: str) -> str:
    clean = _strip_html(content)

    # If we have a link and existing content is thin, fetch the full article
    if link and _content_is_thin(content):
        fetched = await _fetch_article_content(link)
        if fetched and len(fetched.strip()) > len(clean.strip()):
            return _truncate(fetched)

    return _truncate(clean)


# Default models per provider
DEFAULT_MODELS = {
    "anthropic": "claude-haiku-4-5-20251001",
    "openai": "gpt-4o-mini",
    "openrouter": "google/gemini-2.0-flash-exp:free",
    "gemini": "gemini-2.0-flash",
    "ollama": "llama3.2",
}


async def summarize_item(
    title: str, content: str,
    provider: str = "anthropic", api_key: str = "", link: str = "",
    model: str = "", base_url: str = "",
) -> str:
    # Owner disabled summarisation. Guard the service itself so an old queued
    # task or stale client cannot fetch article content or spend provider tokens.
    raise ValueError("AI summarisation is disabled")


def _clean_summary(raw: str, fallback_content: str = "", fallback_title: str = "") -> str:
    """Strip markdown prefixes and reject refusals, fall back to snippet if needed."""
    if not raw:
        return fallback_title[:250] if fallback_title else ""

    text = raw.strip()

    # Strip markdown headers and common preambles
    import re
    text = re.sub(r'^#+\s*(Summary|Article|Overview)\s*:?\s*\n+', '', text, flags=re.IGNORECASE)
    text = re.sub(r'^(Summary|Here\'s a summary|Here is a summary)\s*:?\s*', '', text, flags=re.IGNORECASE)

    # Detect refusal patterns
    lower = text.lower()
    refusal_phrases = [
        "i don't see",
        "i do not see",
        "i would need",
        "i'd be happy to",
        "i cannot provide",
        "i can't provide",
        "could you please share",
        "could you please provide",
        "please share the full",
        "appears to be cut off",
        "appears to be incomplete",
        "content appears to be",
        "the article text appears",
        "not provided",
        "the full article text",
    ]
    if any(phrase in lower for phrase in refusal_phrases):
        # Refusal — fall back to a snippet of the content
        snippet = fallback_content.strip()[:300]
        if snippet:
            return snippet + ("…" if len(fallback_content.strip()) > 300 else "")
        return fallback_title[:250]

    return text.strip()


async def extract_entities(
    title: str, content: str,
    provider: str = "anthropic", api_key: str = "", link: str = "",
    model: str = "", base_url: str = "",
) -> dict:
    clean = await _get_content(content, link)
    prompt = (
        f"Extract structured entities from this article. Return valid JSON with these keys:\n"
        f"- people: list of person names mentioned\n"
        f"- organizations: list of company/org names\n"
        f"- technologies: list of technologies, tools, or languages mentioned\n"
        f"- locations: list of places mentioned\n"
        f"- topics: list of 3-5 topic tags\n\n"
        f"Title: {title}\n\n"
        f"Content: {clean}\n\n"
        f"Return ONLY valid JSON, no other text."
    )

    try:
        result = await _call_llm(prompt, provider, max_tokens=500, api_key=api_key, model=model, base_url=base_url)
    except Exception:
        await record_usage(provider, model or DEFAULT_MODELS.get(provider, ""), status="failed")
        raise

    try:
        return json.loads(result)
    except json.JSONDecodeError:
        import re
        match = re.search(r'\{[\s\S]*\}', result)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return {"error": "Failed to parse entities", "raw": result}


async def _call_llm(
    prompt: str, provider: str = "anthropic", max_tokens: int = 300,
    api_key: str = "", model: str = "", base_url: str = "",
) -> str:
    model = model or DEFAULT_MODELS.get(provider, "")

    if provider == "anthropic":
        return await _call_anthropic(prompt, max_tokens, api_key, model)
    elif provider == "openai":
        return await _call_openai_compatible(
            prompt, max_tokens, api_key, model,
            base_url="https://api.openai.com/v1",
            env_key="OPENAI_API_KEY",
            provider=provider,
        )
    elif provider == "openrouter":
        return await _call_openai_compatible(
            prompt, max_tokens, api_key, model,
            base_url="https://openrouter.ai/api/v1",
            env_key="OPENROUTER_API_KEY",
            provider=provider,
            extra_headers={
                "HTTP-Referer": "https://feedwire.local",
                "X-Title": "FeedWire",
            },
        )
    elif provider == "ollama":
        return await _call_openai_compatible(
            prompt, max_tokens, api_key or "ollama", model,
            base_url=base_url or "http://host.docker.internal:11434/v1",
            env_key=None,
            provider=provider,
        )
    elif provider == "gemini":
        return await _call_gemini(prompt, max_tokens, api_key, model)
    else:
        raise ValueError(f"Unknown provider: {provider}")


async def _call_anthropic(prompt: str, max_tokens: int, api_key: str = "", model: str = "") -> str:
    api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not configured")

    from anthropic import AsyncAnthropic
    client = AsyncAnthropic(api_key=api_key)

    message = await client.messages.create(
        model=model or DEFAULT_MODELS["anthropic"],
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )

    await record_usage("anthropic", message.model or model, message.usage)
    await client.close()
    return message.content[0].text


async def _call_openai_compatible(
    prompt: str, max_tokens: int, api_key: str, model: str,
    base_url: str, env_key: str | None = None,
    extra_headers: dict | None = None,
    provider: str = "openai",
) -> str:
    if env_key:
        api_key = api_key or os.getenv(env_key, "")
    if not api_key:
        raise ValueError(f"API key not configured for {base_url}")

    from openai import AsyncOpenAI
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
        default_headers=extra_headers or {},
    )

    response = await client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )

    usage = response.usage.model_dump() if response.usage else None
    await record_usage(provider, response.model or model, usage,
                       reported_cost=usage.get("cost") if usage else None)
    await client.close()
    return response.choices[0].message.content or ""


async def _call_gemini(prompt: str, max_tokens: int, api_key: str = "", model: str = "") -> str:
    api_key = api_key or os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not configured")

    from google import genai
    client = genai.Client(api_key=api_key)

    response = await client.aio.models.generate_content(
        model=model or DEFAULT_MODELS["gemini"],
        contents=prompt,
        config={"max_output_tokens": max_tokens},
    )

    await record_usage("gemini", model or DEFAULT_MODELS["gemini"], response.usage_metadata)
    return response.text or ""

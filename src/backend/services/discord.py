import httpx
import re
from typing import Optional
from bs4 import BeautifulSoup
from html import unescape

import logging

logger = logging.getLogger(__name__)


def _clean_text(html: str) -> str:
    if not html:
        return ""
    text = BeautifulSoup(html, "lxml").get_text(separator=" ")
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


async def send_webhook(
    webhook_url: str,
    content: Optional[str] = None,
    embeds: Optional[list[dict]] = None,
    username: str = "FeedWire",
    avatar_url: Optional[str] = None,
) -> tuple[bool, str]:
    """Send a message to a Discord webhook. Returns (success, error_msg)."""
    payload = {"username": username}
    if content:
        payload["content"] = content[:2000]
    if embeds:
        payload["embeds"] = embeds[:10]
    if avatar_url:
        payload["avatar_url"] = avatar_url

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(webhook_url, json=payload)
            if response.status_code >= 400:
                body = response.text[:500]
                logger.error(f"Discord webhook {response.status_code}: {body}")
                return False, f"Discord {response.status_code}: {body}"
        return True, ""
    except Exception as e:
        logger.exception("Discord webhook exception")
        return False, str(e)


def build_item_embed(item, feed_title: str = "", summary: str = "") -> dict:
    """Build a Discord embed for a feed item."""
    description = summary or (item.content or "")[:300]
    if len(description) > 300:
        description = description[:297] + "..."

    embed = {
        "title": (item.title or "Untitled")[:256],
        "url": item.link or "",
        "description": description,
        "color": 0x3b82f6,  # brand blue
    }

    if feed_title:
        embed["author"] = {"name": feed_title}

    if item.published_at:
        embed["timestamp"] = item.published_at.isoformat()

    if item.author:
        embed["footer"] = {"text": f"by {item.author}"}

    return embed


def build_digest_embed(
    category: str,
    entries: list[dict],
    max_fields: int = 5,
    max_value_chars: int = 400,
) -> dict:
    """Build a Discord embed for a digest category.

    Each field is kept small to fit within Discord's 6000-char total embed limit.
    Max 5 fields at ~450 chars each ≈ 2250 chars per category embed.
    """
    fields = []
    for entry in entries[:max_fields]:
        title = entry.get("title", "Untitled")
        link = entry.get("link", "")
        summary = entry.get("summary", "") or (entry.get("content") or "")
        summary = _clean_text(summary)

        if summary:
            value_text = summary[:max_value_chars]
            if len(summary) > max_value_chars:
                value_text += "…"
        else:
            value_text = "—"

        if link:
            # Keep link compact by using markdown
            value_text = f"{value_text}\n[→ Read]({link})"

        fields.append({
            "name": title[:200],
            "value": value_text[:1024],
            "inline": False,
        })

    return {
        "title": f"📰 {category}",
        "color": 0x3b82f6,
        "fields": fields,
    }

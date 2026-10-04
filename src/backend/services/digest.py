"""Daily digest generation."""
import math
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from models import Item, Feed, Category
from sqlalchemy import select, func, or_
from services.discord import send_webhook, build_digest_embed
from services.dedup import same_story
from services.semantic import embeddings_for_items


async def generate_digest(
    session,
    hours: int = 24,
    provider: str = "anthropic",
    api_key: str = "",
    model: str = "",
    base_url: str = "",
    max_items_per_category: int = 5,
    max_items_per_feed: int = 2,
    summarize_items: bool = False,
) -> dict[str, list[dict]]:
    """Generate a digest of items from the last N hours, grouped by category.

    Greedy assignment by relevance: items are walked from highest score down, and
    each gets the first category slot it fits in. Dedup is GLOBAL (a wire story
    that lands in multiple categories only shows up in its highest-relevance one);
    per-feed cap prevents one chatty feed dominating a category's slots.

    Returns a dict of category_name -> list of plain dicts (not ORM objects)
    to avoid session detachment issues.
    """
    # Ignore legacy settings/callers asking for AI. Digests use source excerpts.
    summarize_items = False
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    items = session.execute(
        select(Item, Feed, Category.name.label("category_name"))
        .join(Feed, Feed.id == Item.feed_id)
        .outerjoin(Category, Category.id == Feed.category_id)
        .where(or_(Item.published_at >= cutoff, Item.created_at >= cutoff))
        .where(or_(Item.published_at >= cutoff, Item.published_at == None))
        .order_by(Item.relevance_score.desc(), Item.published_at.desc())
    ).all()

    if not items:
        return {}

    # Compute per-category active feed count so the per-feed cap is dynamic:
    # categories with only one active feed don't get artificially starved.
    feeds_per_cat: dict[str, set[int]] = defaultdict(set)
    for item, feed, cat_name in items:
        if feed:
            feeds_per_cat[cat_name or "Uncategorized"].add(feed.id)
    cap_per_cat: dict[str, int] = {
        cat: max(max_items_per_feed, math.ceil(max_items_per_category / max(len(feeds), 1)))
        for cat, feeds in feeds_per_cat.items()
    }

    by_category: dict[str, list[dict]] = defaultdict(list)
    seen_items_global: list[Item] = []
    embeddings = embeddings_for_items([row[0] for row in items])
    seen_feed_per_cat: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))

    for item, feed, cat_name in items:
        key = cat_name or "Uncategorized"
        if len(by_category[key]) >= max_items_per_category:
            continue

        # Cross-category dedup: if a similar title already won a slot anywhere,
        # skip this one. Since items are walked in relevance order, the highest
        # scoring instance keeps its slot.
        title = item.title or "Untitled"
        if any(same_story(item, other, embeddings=embeddings) for other in seen_items_global):
            continue

        # Per-feed cap within category — stops one chatty feed monopolising slots
        # when there's diversity available, but relaxes when a category has only
        # one active feed (otherwise we'd artificially leave slots empty).
        feed_id = feed.id if feed else 0
        cap = cap_per_cat.get(key, max_items_per_feed)
        if seen_feed_per_cat[key][feed_id] >= cap:
            continue

        seen_items_global.append(item)
        seen_feed_per_cat[key][feed_id] += 1

        entry = {
            "id": item.id,
            "title": title,
            "link": item.link or "",
            "content": item.content or "",
            "author": item.author or "",
            "published_at": item.published_at.isoformat() if item.published_at else None,
            "feed_title": feed.title if feed else "",
            "summary": "",
        }
        by_category[key].append(entry)

    return dict(by_category)


def _embed_char_count(embed: dict) -> int:
    """Approximate character count for a Discord embed (6000 total limit)."""
    n = len(embed.get("title", "")) + len(embed.get("description", ""))
    for f in embed.get("fields", []):
        n += len(f.get("name", "")) + len(f.get("value", ""))
    author = embed.get("author", {})
    if isinstance(author, dict):
        n += len(author.get("name", ""))
    footer = embed.get("footer", {})
    if isinstance(footer, dict):
        n += len(footer.get("text", ""))
    return n


async def send_digest_to_discord(
    digest: dict[str, list[dict]],
    webhook_url: str,
    hours: int = 24,
) -> tuple[bool, str]:
    """Send a digest to a Discord webhook. Returns (success, error_msg).

    Respects Discord limits: 10 embeds per message, 6000 chars total per message,
    1024 chars per field value.
    """
    if not digest:
        return False, "Empty digest"

    total_items = sum(len(items) for items in digest.values())
    header = (
        f"**📰 FeedWire Daily Digest** — "
        f"{total_items} stories from the last {hours}h, "
        f"across {len(digest)} {'category' if len(digest) == 1 else 'categories'}"
    )

    # Build all embeds
    all_embeds = []
    for category, items in digest.items():
        all_embeds.append(build_digest_embed(category, items))

    # Batch by BOTH embed count (max 10) and total char count (max ~5500 to leave headroom)
    MAX_CHARS = 5500
    MAX_EMBEDS = 10

    first = True
    batch: list[dict] = []
    batch_chars = 0

    async def flush_batch():
        nonlocal first, batch, batch_chars
        if not batch:
            return True, ""
        content = header if first else None
        ok, err = await send_webhook(webhook_url, content=content, embeds=batch)
        batch = []
        batch_chars = 0
        first = False
        return ok, err

    for embed in all_embeds:
        chars = _embed_char_count(embed)
        if batch and (len(batch) >= MAX_EMBEDS or batch_chars + chars > MAX_CHARS):
            ok, err = await flush_batch()
            if not ok:
                return False, err
        batch.append(embed)
        batch_chars += chars

    ok, err = await flush_batch()
    if not ok:
        return False, err

    return True, ""

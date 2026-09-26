import re
from collections import Counter, defaultdict
from models import Item, UserAction
from services.clustering import extract_keywords


def compute_relevance_scores(
    items: list[Item],
    actions: list[UserAction],
) -> dict[int, float]:
    """Compute relevance scores for items based on user behavior."""
    if not actions:
        return {}

    # Build user interest profile from actions
    keyword_scores: Counter = Counter()
    feed_scores: Counter = Counter()
    action_weights = {
        "read": 1.0,
        "save": 3.0,
        "click": 2.0,
        "summarize": 2.5,
        "upvote": 5.0,
        "downvote": -3.0,
    }

    for action in actions:
        weight = action_weights.get(action.action, 1.0)
        if action.feed_id:
            feed_scores[action.feed_id] += weight
        for kw in (action.keywords or []):
            keyword_scores[kw] += weight

    if not keyword_scores and not feed_scores:
        return {}

    # Normalize by absolute max so signed (downvote) weights still scale
    max_kw = max((abs(v) for v in keyword_scores.values()), default=1) or 1
    max_feed = max((abs(v) for v in feed_scores.values()), default=1) or 1

    # Score each item
    scores: dict[int, float] = {}
    for item in items:
        score = 0.0

        # Keyword relevance (-0.6 to 0.6 — negative if matching keywords are downvoted)
        item_keywords = extract_keywords(item.title or "")
        if item_keywords and keyword_scores:
            keyword_hits = sum(keyword_scores.get(kw, 0) for kw in item_keywords)
            score += 0.6 * max(-1.0, min(keyword_hits / (max_kw * 2), 1.0))

        # Feed preference (-0.3 to 0.3)
        if item.feed_id in feed_scores:
            score += 0.3 * max(-1.0, min(feed_scores[item.feed_id] / max_feed, 1.0))

        # Recency bonus (0-0.1)
        if item.published_at:
            from datetime import datetime, timezone, timedelta
            age_hours = (datetime.now(timezone.utc) - item.published_at).total_seconds() / 3600
            if age_hours < 1:
                score += 0.1
            elif age_hours < 6:
                score += 0.05
            elif age_hours < 24:
                score += 0.02

        scores[item.id] = round(score, 4)

    return scores


def record_action(item: Item, action_type: str) -> dict:
    """Create data for a UserAction record."""
    keywords = extract_keywords(item.title or "")
    return {
        "item_id": item.id,
        "action": action_type,
        "feed_id": item.feed_id,
        "keywords": keywords,
    }

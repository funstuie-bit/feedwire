import asyncio
import os
from datetime import datetime, timezone, timedelta
from celery_app import celery
from database import SyncSession
from models import Feed, Item, Rule, Note, UserAction, Setting
from sqlalchemy import select, update, func
from services.feed_parser import fetch_and_parse_feed
from services.rule_engine import evaluate_rule, get_rule_actions
from services.ai_service import extract_entities, DEFAULT_MODELS
from services.discord import send_webhook, build_item_embed
from services.digest import generate_digest, send_digest_to_discord


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery.task(name="tasks.fetch_all_feeds")
def fetch_all_feeds():
    session = SyncSession()
    try:
        now = datetime.now(timezone.utc)
        feeds = session.execute(select(Feed)).scalars().all()

        for feed in feeds:
            if feed.last_fetched_at:
                interval = timedelta(minutes=feed.fetch_interval_minutes or 30)
                if now - feed.last_fetched_at < interval:
                    continue

            fetch_single_feed.delay(feed.id)
    finally:
        session.close()


# No rate_limit: Celery's rate_limit is per worker node, so "10/m" throttled the
# ENTIRE feed system to 10 fetches/minute — far below the fan-out from ~200 feeds,
# so any burst built a backlog the worker could never drain (the Jul 2026 383k
# pile-up). Per-feed politeness is already handled by feed.fetch_interval_minutes
# in fetch_all_feeds; concurrency bounds parallelism. See docs/handover.md §4.13.
@celery.task(name="tasks.fetch_single_feed")
def fetch_single_feed(feed_id: int):
    session = SyncSession()
    try:
        feed = session.get(Feed, feed_id)
        if not feed:
            return

        try:
            parsed = _run_async(fetch_and_parse_feed(feed.url))
        except Exception as e:
            feed.last_error = str(e)
            feed.error_count = (feed.error_count or 0) + 1
            session.commit()
            return

        new_items = []
        for item_data in parsed["items"]:
            published = item_data.get("published_at")
            if (
                os.getenv("PUBLIC_FRESH_FEEDS", "false").lower() == "true"
                and published is not None
                and feed.created_at is not None
                and published < feed.created_at
            ):
                continue
            existing = session.execute(
                select(Item).where(
                    Item.feed_id == feed.id, Item.guid == item_data["guid"]
                )
            ).scalar_one_or_none()

            if not existing:
                item = Item(feed_id=feed.id, **item_data)
                session.add(item)
                session.flush()
                new_items.append(item)

        feed.last_fetched_at = datetime.now(timezone.utc)
        feed.last_error = None
        feed.error_count = 0
        if parsed["feed"]["title"] and not feed.title_custom:
            feed.title = parsed["feed"]["title"]

        session.commit()

        # Process rules against new items
        if new_items:
            rules = session.execute(
                select(Rule).where(Rule.is_active == True)
            ).scalars().all()

            for item in new_items:
                _apply_rules(session, item, rules)

            session.commit()

    finally:
        session.close()


def _apply_rules(session, item: Item, rules: list[Rule]):
    matched = []
    for rule in rules:
        if rule.category_ids:
            feed = session.get(Feed, item.feed_id)
            if feed and feed.category_id not in rule.category_ids:
                continue

        if evaluate_rule(rule, item):
            matched.append(rule.id)
            actions = get_rule_actions(rule)

            for action in actions:
                if action == "summarize":
                    # Historical rules remain intact; this action is disabled.
                    continue

                elif action == "extract_entities" and not item.ai_entities:
                    try:
                        entities = _run_async(
                            extract_entities(item.title or "", item.content or "")
                        )
                        item.ai_entities = entities
                    except Exception:
                        pass

                elif action == "save_to_notes":
                    note = Note(
                        item_id=item.id,
                        title=item.title,
                        content=item.ai_summary or item.title or "",
                    )
                    session.add(note)

                elif action == "hide":
                    item.is_hidden = True

                elif action == "notify_discord":
                    webhook = _get_setting(session, "discord_webhook_url")
                    if webhook:
                        feed = session.get(Feed, item.feed_id)
                        feed_title = feed.title if feed else ""
                        embed = build_item_embed(
                            item, feed_title,
                            summary=item.ai_summary or "",
                        )
                        content = f"🔔 **{rule.name or rule.match_expression}** matched"
                        try:
                            _run_async(send_webhook(webhook, content=content, embeds=[embed]))
                        except Exception:
                            pass

    if matched:
        item.matched_rules = matched


def _get_setting(session, key: str) -> str:
    result = session.execute(select(Setting).where(Setting.key == key)).scalar_one_or_none()
    return result.value if result else ""


def _get_ai_config(session) -> dict:
    result = session.execute(select(Setting)).scalars().all()
    settings = {s.key: s.value for s in result}
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
    return {"provider": provider, "api_key": api_key, "model": model, "base_url": base_url}


@celery.task(name="tasks.send_daily_digest")
def send_daily_digest():
    session = SyncSession()
    try:
        webhook = _get_setting(session, "discord_digest_webhook_url") or _get_setting(session, "discord_webhook_url")
        if not webhook:
            return

        hours = int(_get_setting(session, "digest_hours") or "24")
        max_items = int(_get_setting(session, "digest_max_items_per_category") or "5")
        max_per_feed = int(_get_setting(session, "digest_max_items_per_feed") or "2")
        summarize = False  # Owner disabled summaries, including scheduled digests.

        config = _get_ai_config(session) if summarize else {"provider": "anthropic", "api_key": "", "model": "", "base_url": ""}

        digest = _run_async(generate_digest(
            session,
            hours=hours,
            max_items_per_category=max_items,
            max_items_per_feed=max_per_feed,
            summarize_items=summarize,
            **config,
        ))

        _run_async(send_digest_to_discord(digest, webhook, hours=hours))
    finally:
        session.close()


@celery.task(name="tasks.update_relevance_scores")
def update_relevance_scores():
    from services.scoring import compute_relevance_scores
    session = SyncSession()
    try:
        # Get recent items (last 48h)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
        items = session.execute(
            select(Item).where(Item.created_at >= cutoff)
        ).scalars().all()

        # Get user actions (last 30 days)
        action_cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        actions = session.execute(
            select(UserAction).where(UserAction.created_at >= action_cutoff)
        ).scalars().all()

        if not items or not actions:
            return

        scores = compute_relevance_scores(list(items), list(actions))
        for item in items:
            if item.id in scores:
                item.relevance_score = scores[item.id]

        session.commit()
    finally:
        session.close()


@celery.task(name="tasks.send_score_alerts")
def send_score_alerts():
    """Push high-scoring items to a Discord webhook as they appear."""
    session = SyncSession()
    try:
        if _get_setting(session, "alerts_enabled") != "true":
            return
        webhook = _get_setting(session, "alerts_webhook_url") or _get_setting(session, "discord_webhook_url")
        if not webhook:
            return

        try:
            threshold = float(_get_setting(session, "alerts_score_threshold") or "0.7")
        except ValueError:
            threshold = 0.7
        try:
            max_per_hour = int(_get_setting(session, "alerts_max_per_hour") or "5")
        except ValueError:
            max_per_hour = 5

        from sqlalchemy import func
        now = datetime.now(timezone.utc)
        hour_ago = now - timedelta(hours=1)

        sent_recently = session.execute(
            select(func.count(Item.id)).where(Item.pushed_at >= hour_ago)
        ).scalar_one()
        slots = max_per_hour - sent_recently
        if slots <= 0:
            return

        day_ago = now - timedelta(hours=24)
        candidates = session.execute(
            select(Item).where(
                Item.pushed_at.is_(None),
                Item.is_hidden == False,
                Item.relevance_score >= threshold,
                Item.created_at >= day_ago,
            ).order_by(Item.relevance_score.desc()).limit(slots)
        ).scalars().all()

        for item in candidates:
            feed = session.get(Feed, item.feed_id)
            feed_title = feed.title if feed else ""
            embed = build_item_embed(item, feed_title, summary=item.ai_summary or "")
            content = f"🔥 **Score {item.relevance_score:.2f}** · {feed_title}"
            try:
                ok, _err = _run_async(send_webhook(webhook, content=content, embeds=[embed]))
            except Exception:
                ok = False
            if ok:
                item.pushed_at = now

        session.commit()
    finally:
        session.close()


@celery.task(name="tasks.cleanup_old_items")
def cleanup_old_items(days: int = 90):
    session = SyncSession()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        old_items = session.execute(
            select(Item).where(
                Item.created_at < cutoff,
                Item.is_saved == False,
                ~select(Note.id).where(Note.item_id == Item.id).exists(),
                ~select(UserAction.id).where(UserAction.item_id == Item.id).exists(),
            )
        ).scalars().all()

        for item in old_items:
            session.delete(item)

        session.commit()
    finally:
        session.close()


@celery.task(name="tasks.auto_read_old_items")
def auto_read_old_items(days: int = 7):
    """Bound unread badges to the last week, keeping saved/hidden items intact."""
    if days < 1:
        raise ValueError("days must be positive")
    with SyncSession() as session:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        result = session.execute(
            update(Item).where(
                Item.is_read == False,
                Item.is_hidden == False,
                Item.is_saved == False,
                func.coalesce(Item.published_at, Item.created_at) < cutoff,
            ).values(is_read=True)
        )
        session.commit()
        return {"marked_read": result.rowcount, "days": days}

from fastapi import APIRouter, Depends, HTTPException, Query
import os
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, asc, and_, or_, func, case, text
from sqlalchemy.orm import selectinload
from datetime import datetime, timezone, timedelta
from database import get_db
from models import Item, Feed, Category, UserAction
from schemas import ItemOut, ItemUpdate, BulkItemUpdate, SimilarItem, ClusterOut, TagOut
from services.dedup import find_duplicates, title_similarity
from services.clustering import cluster_items
from services.scoring import compute_relevance_scores, record_action
from services.paywall import is_paywalled, get_archive_url
from services.article_reader import fetch_readable_content
from services.content_sanitizer import sanitize_content

router = APIRouter(prefix="/api/items", tags=["items"])


def _build_item_out(item, feed_title, feed_favicon, similar=None):
    item_dict = {c.name: getattr(item, c.name) for c in Item.__table__.columns}
    item_dict["feed_title"] = feed_title
    item_dict["feed_favicon"] = feed_favicon
    item_dict["similar_items"] = similar or []
    item_dict["tags"] = [TagOut.model_validate(t) for t in (item.tags or [])]
    item_dict["is_paywalled"] = is_paywalled(item.link or "")
    item_dict["archive_url"] = get_archive_url(item.link) if item_dict["is_paywalled"] else None
    if item_dict.get("content"):
        item_dict["content"] = sanitize_content(item_dict["content"], item.link or "")
    return ItemOut(**item_dict)


@router.get("", response_model=list[ItemOut])
async def list_items(
    category_id: int | None = None,
    category_ids: str | None = None,
    feed_id: int | None = None,
    search: str | None = None,
    time_window: str = "24h",
    sort_by: str = "time",
    is_saved: bool | None = None,
    is_hidden: bool | None = None,
    show_hidden: bool = False,
    tag_id: int | None = None,
    unread_only: bool = False,
    deduplicate: bool = True,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Item, Feed.title.label("feed_title"), Feed.favicon_url.label("feed_favicon"))
        .join(Feed, Feed.id == Item.feed_id)
        .options(selectinload(Item.tags))
    )

    window_hours = _parse_time_window(time_window)
    if window_hours:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
        query = query.where(
            or_(Item.published_at >= cutoff, Item.created_at >= cutoff)
        )

    if category_id is not None:
        query = query.where(Feed.category_id == category_id)
    if category_ids is not None:
        try:
            ids = [int(value) for value in category_ids.split(",")]
            if not ids or len(ids) > 100 or any(value <= 0 for value in ids):
                raise ValueError
        except ValueError:
            raise HTTPException(422, "category_ids must contain up to 100 positive category IDs")
        query = query.where(Feed.category_id.in_(ids))
    if feed_id is not None:
        query = query.where(Item.feed_id == feed_id)
    if search:
        # Full-text search using PostgreSQL tsvector with ranking
        # Use plainto_tsquery for safety - handles user input without special syntax
        ts_query = func.plainto_tsquery('english', search)
        query = query.where(
            text("search_vector @@ plainto_tsquery('english', :q)")
        ).params(q=search)
        if sort_by == "time":
            # When searching, default to ranking by relevance to query
            sort_by = "search_rank"
    if is_saved is not None:
        query = query.where(Item.is_saved == is_saved)
    if not show_hidden:
        query = query.where(Item.is_hidden == False)
    if tag_id is not None:
        from models import item_tags
        query = query.join(item_tags, item_tags.c.item_id == Item.id).where(item_tags.c.tag_id == tag_id)
    if unread_only:
        query = query.where(Item.is_read == False)

    if sort_by == "search_rank" and search:
        query = query.order_by(
            text("ts_rank(search_vector, plainto_tsquery('english', :q)) DESC"),
            desc(func.coalesce(Item.published_at, Item.created_at)),
        ).params(q=search)
    elif sort_by == "relevance":
        query = query.order_by(desc(Item.relevance_score), desc(func.coalesce(Item.published_at, Item.created_at)))
    elif sort_by == "title":
        query = query.order_by(asc(Item.title))
    elif sort_by == "source":
        query = query.order_by(asc(Feed.title), desc(Item.published_at))
    else:
        query = query.order_by(desc(func.coalesce(Item.published_at, Item.created_at)))

    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    rows = result.all()

    # Build items
    items_raw = [(item, ft, ff) for item, ft, ff in rows]
    feed_title_map = {item.id: ft for item, ft, ff in items_raw}
    item_map = {item.id: item for item, _, _ in items_raw}

    # Deduplication
    if deduplicate and len(items_raw) > 1:
        all_items = [item for item, _, _ in items_raw]
        dupes = find_duplicates(all_items)
        dupe_children = set()
        for children in dupes.values():
            dupe_children.update(children)

        items = []
        for item, ft, ff in items_raw:
            if item.id in dupe_children:
                continue
            similar = []
            if item.id in dupes:
                for child_id in dupes[item.id]:
                    similar.append(SimilarItem(
                        id=child_id,
                        feed_title=feed_title_map.get(child_id),
                        feed_id=item_map[child_id].feed_id,
                        link=item_map[child_id].link,
                    ))
            items.append(_build_item_out(item, ft, ff, similar))
    else:
        items = [_build_item_out(item, ft, ff) for item, ft, ff in items_raw]

    return items


@router.get("/clusters", response_model=list[ClusterOut])
async def get_clusters(
    time_window: str = "24h",
    db: AsyncSession = Depends(get_db),
):
    query = select(Item).join(Feed, Feed.id == Item.feed_id)
    window_hours = _parse_time_window(time_window)
    if window_hours:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
        query = query.where(
            or_(Item.published_at >= cutoff, Item.created_at >= cutoff)
        )
    query = query.order_by(desc(func.coalesce(Item.published_at, Item.created_at))).limit(300)

    result = await db.execute(query)
    items = result.scalars().all()
    clusters = cluster_items(list(items))

    return [ClusterOut(**c) for c in clusters]


@router.get("/count")
async def item_count(
    time_window: str = "24h",
    db: AsyncSession = Depends(get_db),
):
    query = select(func.count(Item.id))
    window_hours = _parse_time_window(time_window)
    if window_hours:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
        query = query.where(
            or_(Item.published_at >= cutoff, Item.created_at >= cutoff)
        )
    result = await db.execute(query)
    return {"count": result.scalar()}


@router.get("/unread-counts")
async def unread_counts(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Feed.id, func.count(Item.id))
        .join(Item)
        .where(Item.is_read == False, Item.is_hidden == False)
        .group_by(Feed.id)
    )
    counts = {feed_id: count for feed_id, count in result.all()}

    total = await db.execute(
        select(func.count(Item.id)).where(
            Item.is_read == False, Item.is_hidden == False
        )
    )

    return {"feeds": counts, "total": total.scalar()}


@router.get("/{item_id}", response_model=ItemOut)
async def get_item(item_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Item, Feed.title.label("feed_title"), Feed.favicon_url.label("feed_favicon"))
        .join(Feed, Feed.id == Item.feed_id)
        .where(Item.id == item_id)
        .options(selectinload(Item.tags))
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(404, "Item not found")

    item, feed_title, feed_favicon = row
    return _build_item_out(item, feed_title, feed_favicon)


@router.get("/{item_id}/readable")
async def get_readable(item_id: int, db: AsyncSession = Depends(get_db)):
    item = await db.get(Item, item_id)
    if not item:
        raise HTTPException(404, "Item not found")

    if item.cleaned_content:
        return {"content": item.cleaned_content}

    # Public showcase mode serves only text already stored in its own feed DB.
    # Never fetch an arbitrary article URL on behalf of an anonymous visitor.
    if os.getenv("PUBLIC_READ_ONLY", "false").lower() == "true":
        return {"content": item.content or ""}

    if not item.link:
        return {"content": item.content or ""}

    content = await fetch_readable_content(item.link)
    if content:
        item.cleaned_content = content
        await db.commit()

    return {"content": content or item.content or ""}


@router.patch("/{item_id}", response_model=ItemOut)
async def update_item(
    item_id: int, update: ItemUpdate, db: AsyncSession = Depends(get_db)
):
    item = await db.get(Item, item_id)
    if not item:
        raise HTTPException(404, "Item not found")

    if update.is_read is not None:
        item.is_read = update.is_read
        if update.is_read:
            action_data = record_action(item, "read")
            db.add(UserAction(**action_data))

    if update.is_saved is not None:
        item.is_saved = update.is_saved
        if update.is_saved:
            action_data = record_action(item, "save")
            db.add(UserAction(**action_data))

    if update.is_hidden is not None:
        item.is_hidden = update.is_hidden

    if update.feedback is not None:
        clamped = max(-1, min(1, int(update.feedback)))
        item.feedback = clamped
        if clamped == 1:
            db.add(UserAction(**record_action(item, "upvote")))
        elif clamped == -1:
            db.add(UserAction(**record_action(item, "downvote")))

    await db.commit()
    await db.refresh(item, attribute_names=["tags"])

    feed = await db.get(Feed, item.feed_id)
    return _build_item_out(
        item,
        feed.title if feed else None,
        feed.favicon_url if feed else None,
    )


@router.post("/bulk-update")
async def bulk_update(update: BulkItemUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Item).where(Item.id.in_(update.item_ids))
    )
    items = result.scalars().all()
    for item in items:
        if update.is_read is not None:
            item.is_read = update.is_read
        if update.is_saved is not None:
            item.is_saved = update.is_saved
    await db.commit()
    return {"updated": len(items)}


@router.post("/mark-all-read")
async def mark_all_read(
    category_id: int | None = None,
    feed_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Item).where(Item.is_read == False)
    if feed_id:
        query = query.where(Item.feed_id == feed_id)
    elif category_id:
        query = query.join(Feed, Feed.id == Item.feed_id).where(Feed.category_id == category_id)

    result = await db.execute(query)
    items = result.scalars().all()
    for item in items:
        item.is_read = True
    await db.commit()
    return {"marked": len(items)}


def _parse_time_window(window: str) -> int | None:
    if not window or window == "all":
        return None
    match = {
        "1h": 1, "3h": 3, "6h": 6, "12h": 12,
        "24h": 24, "48h": 48, "7d": 168, "30d": 720,
    }
    return match.get(window, 24)

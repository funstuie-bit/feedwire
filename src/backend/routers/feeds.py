from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case, and_
from datetime import datetime, timezone, timedelta
from database import get_db
from models import Feed, Category, Item
from schemas import FeedCreate, FeedOut, OPMLImport, SyntheticFeedCreate
from services.feed_parser import (
    fetch_and_parse_feed, discover_feed_url, parse_opml, generate_opml
)
from services.synthetic import create_synthetic_feed

router = APIRouter(prefix="/api/feeds", tags=["feeds"])


@router.get("", response_model=list[FeedOut])
async def list_feeds(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(
            Feed,
            func.count(Item.id).label("item_count"),
            func.count(case((and_(Item.is_read == False, Item.is_hidden == False), 1))).label("unread_count"),
        )
        .outerjoin(Item)
        .group_by(Feed.id)
        .order_by(Feed.title)
    )
    feeds = []
    for feed, count, unread in result.all():
        feed_dict = {
            "id": feed.id,
            "url": feed.url,
            "title": feed.title,
            "description": feed.description,
            "site_url": feed.site_url,
            "favicon_url": feed.favicon_url,
            "category_id": feed.category_id,
            "is_private": feed.is_private,
            "fetch_interval_minutes": feed.fetch_interval_minutes,
            "last_fetched_at": feed.last_fetched_at,
            "last_error": feed.last_error,
            "error_count": feed.error_count,
            "item_count": count,
            "unread_count": unread,
            "created_at": feed.created_at,
        }
        feeds.append(FeedOut(**feed_dict))
    return feeds


@router.post("", response_model=FeedOut)
async def add_feed(feed_in: FeedCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Feed).where(Feed.url == feed_in.url))
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Feed already exists")

    try:
        parsed = await fetch_and_parse_feed(feed_in.url)
    except Exception as e:
        # Maybe it's a page URL, try to discover the feed
        try:
            discovered = await discover_feed_url(feed_in.url)
            if discovered:
                parsed = await fetch_and_parse_feed(discovered)
                feed_in.url = discovered
            else:
                raise HTTPException(400, f"Could not find or parse feed: {e}")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(400, f"Could not find or parse feed: {e}")

    feed = Feed(
        url=feed_in.url,
        title=parsed["feed"]["title"] or feed_in.url,
        description=parsed["feed"]["description"],
        site_url=parsed["feed"]["site_url"],
        favicon_url=parsed["feed"]["favicon_url"],
        category_id=feed_in.category_id,
        is_private=feed_in.is_private,
        fetch_interval_minutes=feed_in.fetch_interval_minutes,
    )
    db.add(feed)
    await db.flush()

    seen_guids = set()
    for item_data in parsed["items"]:
        guid = item_data.get("guid")
        if guid and guid in seen_guids:
            continue
        if guid:
            seen_guids.add(guid)
        db.add(Item(feed_id=feed.id, **item_data))

    await db.commit()
    await db.refresh(feed)

    return FeedOut(
        **{c.name: getattr(feed, c.name) for c in Feed.__table__.columns},
        item_count=len(parsed["items"]),
        unread_count=len(parsed["items"]),
    )


@router.patch("/{feed_id}")
async def update_feed(feed_id: int, data: dict, db: AsyncSession = Depends(get_db)):
    feed = await db.get(Feed, feed_id)
    if not feed:
        raise HTTPException(404, "Feed not found")

    if "category_id" in data:
        feed.category_id = data["category_id"]
    if "title" in data:
        feed.title = data["title"]
        feed.title_custom = True
    if "fetch_interval_minutes" in data:
        feed.fetch_interval_minutes = data["fetch_interval_minutes"]
    if "is_private" in data:
        feed.is_private = data["is_private"]

    await db.commit()
    await db.refresh(feed)
    return {"ok": True}


@router.delete("/{feed_id}")
async def delete_feed(feed_id: int, db: AsyncSession = Depends(get_db)):
    feed = await db.get(Feed, feed_id)
    if not feed:
        raise HTTPException(404, "Feed not found")
    await db.delete(feed)
    await db.commit()
    return {"ok": True}


@router.post("/{feed_id}/refresh")
async def refresh_feed(feed_id: int, db: AsyncSession = Depends(get_db)):
    feed = await db.get(Feed, feed_id)
    if not feed:
        raise HTTPException(404, "Feed not found")

    try:
        parsed = await fetch_and_parse_feed(feed.url)
    except Exception as e:
        feed.last_error = str(e)
        feed.error_count = (feed.error_count or 0) + 1
        await db.commit()
        raise HTTPException(502, f"Failed to fetch feed: {e}")

    new_count = 0
    for item_data in parsed["items"]:
        existing = await db.execute(
            select(Item).where(Item.feed_id == feed.id, Item.guid == item_data["guid"])
        )
        if not existing.scalar_one_or_none():
            db.add(Item(feed_id=feed.id, **item_data))
            new_count += 1

    from datetime import datetime, timezone
    feed.last_fetched_at = datetime.now(timezone.utc)
    feed.last_error = None
    feed.error_count = 0
    if parsed["feed"]["title"] and not feed.title_custom:
        feed.title = parsed["feed"]["title"]

    await db.commit()
    return {"ok": True, "new_items": new_count}


@router.post("/discover")
async def discover_feed(data: dict, db: AsyncSession = Depends(get_db)):
    url = data.get("url", "")
    if not url:
        raise HTTPException(400, "URL required")
    found = await discover_feed_url(url)
    if found:
        return {"feed_url": found}
    raise HTTPException(404, "No feed found at that URL")


@router.post("/import-opml")
async def import_opml(data: OPMLImport, db: AsyncSession = Depends(get_db)):
    import asyncio

    feeds = parse_opml(data.content)
    imported = 0
    errors = []

    for feed_data in feeds:
        existing = await db.execute(select(Feed).where(Feed.url == feed_data["url"]))
        if existing.scalar_one_or_none():
            continue

        category_id = None
        if feed_data.get("category"):
            cat_result = await db.execute(
                select(Category).where(Category.name == feed_data["category"])
            )
            cat = cat_result.scalar_one_or_none()
            if not cat:
                cat = Category(name=feed_data["category"])
                db.add(cat)
                await db.flush()
            category_id = cat.id

        try:
            parsed = await asyncio.wait_for(
                fetch_and_parse_feed(feed_data["url"]), timeout=30.0
            )
            feed = Feed(
                url=feed_data["url"],
                title=parsed["feed"]["title"] or feed_data.get("title", ""),
                description=parsed["feed"]["description"],
                site_url=parsed["feed"]["site_url"],
                favicon_url=parsed["feed"]["favicon_url"],
                category_id=category_id,
            )
            db.add(feed)
            await db.flush()

            seen_guids = set()
            for item_data in parsed["items"]:
                guid = item_data.get("guid")
                if guid and guid in seen_guids:
                    continue
                if guid:
                    seen_guids.add(guid)
                db.add(Item(feed_id=feed.id, **item_data))

            await db.flush()
            imported += 1
        except asyncio.TimeoutError:
            await db.rollback()
            errors.append({"url": feed_data["url"], "error": "Timeout after 30s"})
        except Exception as e:
            await db.rollback()
            errors.append({"url": feed_data["url"], "error": str(e)[:200] or type(e).__name__})

    await db.commit()
    return {"imported": imported, "errors": errors}


@router.get("/export-opml")
async def export_opml(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Feed, Category.name.label("category_name"))
        .outerjoin(Category)
        .order_by(Category.name, Feed.title)
    )

    feeds = []
    for feed, cat_name in result.all():
        feeds.append({
            "url": feed.url,
            "title": feed.title or "",
            "site_url": feed.site_url or "",
            "category": cat_name or "Uncategorized",
        })

    opml_content = generate_opml(feeds)
    return Response(
        content=opml_content,
        media_type="application/xml",
        headers={"Content-Disposition": "attachment; filename=feedwire-export.opml"},
    )


@router.post("/synthetic", response_model=FeedOut)
async def add_synthetic_feed(
    data: SyntheticFeedCreate, db: AsyncSession = Depends(get_db)
):
    existing = await db.execute(select(Feed).where(Feed.url == data.page_url))
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Feed for this URL already exists")

    try:
        parsed = await create_synthetic_feed(data.page_url)
    except Exception as e:
        raise HTTPException(400, f"Could not create synthetic feed: {e}")

    if not parsed["items"]:
        raise HTTPException(400, "No content found on that page")

    feed = Feed(
        url=data.page_url,
        title=parsed["feed"]["title"],
        description=parsed["feed"]["description"],
        site_url=parsed["feed"]["site_url"],
        favicon_url=parsed["feed"]["favicon_url"],
        category_id=data.category_id,
    )
    db.add(feed)
    await db.flush()

    for item_data in parsed["items"]:
        db.add(Item(feed_id=feed.id, **item_data))

    await db.commit()
    await db.refresh(feed)

    return FeedOut(
        **{c.name: getattr(feed, c.name) for c in Feed.__table__.columns},
        item_count=len(parsed["items"]),
        unread_count=len(parsed["items"]),
    )


@router.get("/health")
async def feed_health(db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(hours=24)
    week_ago = now - timedelta(days=7)

    result = await db.execute(
        select(
            Feed,
            Category.name.label("category_name"),
            func.count(Item.id).label("total_items"),
            func.count(case((Item.created_at >= day_ago, 1))).label("items_24h"),
            func.count(case((Item.created_at >= week_ago, 1))).label("items_7d"),
            func.max(Item.published_at).label("latest_item"),
        )
        .outerjoin(Category, Category.id == Feed.category_id)
        .outerjoin(Item, Item.feed_id == Feed.id)
        .group_by(Feed.id, Category.name)
        .order_by(Feed.error_count.desc(), Feed.title)
    )

    feeds = []
    for feed, cat_name, total, day_count, week_count, latest in result.all():
        days_since_item = (now - latest).days if latest else None
        status = "healthy"
        if feed.error_count >= 5:
            status = "error"
        elif feed.error_count >= 1:
            status = "warning"
        elif days_since_item and days_since_item > 14:
            status = "inactive"
        elif days_since_item and days_since_item > 7:
            status = "stale"

        feeds.append({
            "id": feed.id,
            "title": feed.title or feed.url,
            "url": feed.url,
            "category": cat_name or "Uncategorized",
            "status": status,
            "error_count": feed.error_count,
            "last_error": feed.last_error,
            "last_fetched_at": feed.last_fetched_at.isoformat() if feed.last_fetched_at else None,
            "latest_item_at": latest.isoformat() if latest else None,
            "days_since_item": days_since_item,
            "total_items": total,
            "items_24h": day_count,
            "items_7d": week_count,
        })

    return feeds

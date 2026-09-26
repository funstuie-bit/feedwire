from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case, and_
from database import get_db
from models import Category, Feed, Item
from schemas import CategoryCreate, CategoryOut, CategoryUpdate

router = APIRouter(prefix="/api/categories", tags=["categories"])


@router.get("", response_model=list[CategoryOut])
async def list_categories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(
            Category,
            func.count(func.distinct(Feed.id)).label("feed_count"),
            func.count(case((and_(Item.is_read == False, Item.is_hidden == False), 1))).label("unread_count"),
        )
        .outerjoin(Feed, Feed.category_id == Category.id)
        .outerjoin(Item, Item.feed_id == Feed.id)
        .group_by(Category.id)
        .order_by(Category.sort_order, Category.name)
    )
    categories = []
    for cat, feed_count, unread_count in result.all():
        categories.append(CategoryOut(
            id=cat.id,
            name=cat.name,
            sort_order=cat.sort_order,
            group_name=cat.group_name,
            feed_count=feed_count,
            unread_count=unread_count,
        ))
    return categories


@router.post("", response_model=CategoryOut)
async def create_category(
    cat_in: CategoryCreate, db: AsyncSession = Depends(get_db)
):
    existing = await db.execute(
        select(Category).where(Category.name == cat_in.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Category already exists")

    cat = Category(**cat_in.model_dump())
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return CategoryOut(
        id=cat.id, name=cat.name, sort_order=cat.sort_order,
        group_name=cat.group_name, feed_count=0, unread_count=0,
    )


@router.patch("/{category_id}", response_model=CategoryOut)
async def update_category(
    category_id: int, cat_in: CategoryUpdate, db: AsyncSession = Depends(get_db)
):
    cat = await db.get(Category, category_id)
    if not cat:
        raise HTTPException(404, "Category not found")

    payload = cat_in.model_dump(exclude_unset=True)
    # Treat empty string as null for group_name so the UI can "ungroup".
    if "group_name" in payload and payload["group_name"] == "":
        payload["group_name"] = None
    for field, value in payload.items():
        setattr(cat, field, value)
    await db.commit()
    await db.refresh(cat)

    counts = await db.execute(
        select(
            func.count(func.distinct(Feed.id)),
            func.count(case((and_(Item.is_read == False, Item.is_hidden == False), 1))),
        )
        .outerjoin(Feed, Feed.category_id == Category.id)
        .outerjoin(Item, Item.feed_id == Feed.id)
        .where(Category.id == category_id)
    )
    feed_count, unread_count = counts.one()
    return CategoryOut(
        id=cat.id, name=cat.name, sort_order=cat.sort_order,
        group_name=cat.group_name, feed_count=feed_count, unread_count=unread_count,
    )


@router.delete("/{category_id}")
async def delete_category(category_id: int, db: AsyncSession = Depends(get_db)):
    cat = await db.get(Category, category_id)
    if not cat:
        raise HTTPException(404, "Category not found")

    result = await db.execute(
        select(Feed).where(Feed.category_id == category_id)
    )
    for feed in result.scalars().all():
        feed.category_id = None

    await db.delete(cat)
    await db.commit()
    return {"ok": True}

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from models import Tag, Item, item_tags
from schemas import TagOut, TagCreate

router = APIRouter(prefix="/api/tags", tags=["tags"])


@router.get("", response_model=list[TagOut])
async def list_tags(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Tag).order_by(Tag.name))
    return result.scalars().all()


@router.post("", response_model=TagOut)
async def create_tag(data: TagCreate, db: AsyncSession = Depends(get_db)):
    tag = Tag(name=data.name, color=data.color)
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    return tag


@router.delete("/{tag_id}")
async def delete_tag(tag_id: int, db: AsyncSession = Depends(get_db)):
    tag = await db.get(Tag, tag_id)
    if not tag:
        raise HTTPException(404, "Tag not found")
    await db.delete(tag)
    await db.commit()
    return {"deleted": True}


@router.post("/items/{item_id}/{tag_id}")
async def add_tag_to_item(item_id: int, tag_id: int, db: AsyncSession = Depends(get_db)):
    item = await db.get(Item, item_id)
    tag = await db.get(Tag, tag_id)
    if not item or not tag:
        raise HTTPException(404, "Item or tag not found")
    await db.execute(item_tags.insert().values(item_id=item_id, tag_id=tag_id).prefix_with("OR IGNORE"))
    await db.commit()
    return {"ok": True}


@router.delete("/items/{item_id}/{tag_id}")
async def remove_tag_from_item(item_id: int, tag_id: int, db: AsyncSession = Depends(get_db)):
    await db.execute(item_tags.delete().where(item_tags.c.item_id == item_id, item_tags.c.tag_id == tag_id))
    await db.commit()
    return {"ok": True}

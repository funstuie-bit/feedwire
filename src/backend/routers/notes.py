from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from models import Note, Item
from schemas import NoteCreate, NoteOut

router = APIRouter(prefix="/api/notes", tags=["notes"])


@router.get("", response_model=list[NoteOut])
async def list_notes(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Note, Item.title.label("item_title"))
        .outerjoin(Item)
        .order_by(Note.created_at.desc())
    )
    notes = []
    for note, item_title in result.all():
        notes.append(NoteOut(
            id=note.id,
            item_id=note.item_id,
            title=note.title,
            content=note.content,
            item_title=item_title,
            created_at=note.created_at,
        ))
    return notes


@router.post("", response_model=NoteOut)
async def create_note(note_in: NoteCreate, db: AsyncSession = Depends(get_db)):
    note = Note(**note_in.model_dump())
    db.add(note)
    await db.commit()
    await db.refresh(note)

    item_title = None
    if note.item_id:
        item = await db.get(Item, note.item_id)
        item_title = item.title if item else None

    return NoteOut(
        id=note.id,
        item_id=note.item_id,
        title=note.title,
        content=note.content,
        item_title=item_title,
        created_at=note.created_at,
    )


@router.delete("/{note_id}")
async def delete_note(note_id: int, db: AsyncSession = Depends(get_db)):
    note = await db.get(Note, note_id)
    if not note:
        raise HTTPException(404, "Note not found")
    await db.delete(note)
    await db.commit()
    return {"ok": True}

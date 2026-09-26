from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from models import Setting
from schemas import SettingUpdate, SettingsOut

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=SettingsOut)
async def get_settings(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Setting))
    settings = {s.key: s.value for s in result.scalars().all()}
    return SettingsOut(settings=settings)


@router.patch("")
async def update_settings(
    updates: list[SettingUpdate], db: AsyncSession = Depends(get_db)
):
    for update in updates:
        result = await db.execute(
            select(Setting).where(Setting.key == update.key)
        )
        setting = result.scalar_one_or_none()
        if setting:
            setting.value = update.value
        else:
            db.add(Setting(key=update.key, value=update.value))

    await db.commit()
    return {"ok": True}

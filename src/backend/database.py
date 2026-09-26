import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://feedwire:feedwire_dev@localhost:5432/feedwire")
DATABASE_URL_SYNC = os.getenv("DATABASE_URL_SYNC", "postgresql://feedwire:feedwire_dev@localhost:5432/feedwire")

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

sync_engine = create_engine(DATABASE_URL_SYNC, echo=False)
SyncSession = sessionmaker(sync_engine)


async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


def get_sync_db():
    session = SyncSession()
    try:
        yield session
    finally:
        session.close()

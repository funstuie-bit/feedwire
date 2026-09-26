from contextlib import asynccontextmanager
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from database import engine
from models import Base
from routers import feeds, items, rules, notes, ai, categories, settings, digest, tags


async def _migrate_columns(conn):
    """Add new columns to existing tables if they don't exist."""
    from sqlalchemy import text
    migrations = [
        "ALTER TABLE items ADD COLUMN IF NOT EXISTS cleaned_content TEXT",
        "ALTER TABLE items ADD COLUMN IF NOT EXISTS cluster_id VARCHAR(100)",
        "ALTER TABLE items ADD COLUMN IF NOT EXISTS dedup_hash VARCHAR(64)",
        "ALTER TABLE items ADD COLUMN IF NOT EXISTS relevance_score FLOAT DEFAULT 0.0",
        "ALTER TABLE feeds ADD COLUMN IF NOT EXISTS title_custom BOOLEAN DEFAULT FALSE",
        "ALTER TABLE items ADD COLUMN IF NOT EXISTS is_hidden BOOLEAN DEFAULT FALSE",
        "CREATE INDEX IF NOT EXISTS ix_items_hidden ON items (is_hidden)",
        # Full-text search tsvector column, auto-generated
        """ALTER TABLE items ADD COLUMN IF NOT EXISTS search_vector tsvector
           GENERATED ALWAYS AS (
             setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
             setweight(to_tsvector('english', coalesce(content, '')), 'B') ||
             setweight(to_tsvector('english', coalesce(author, '')), 'C')
           ) STORED""",
        "CREATE INDEX IF NOT EXISTS ix_items_search_vector ON items USING GIN (search_vector)",
        "ALTER TABLE items ADD COLUMN IF NOT EXISTS feedback INTEGER DEFAULT 0",
        "CREATE INDEX IF NOT EXISTS ix_items_feedback ON items (feedback)",
        "ALTER TABLE items ADD COLUMN IF NOT EXISTS pushed_at TIMESTAMPTZ",
        "CREATE INDEX IF NOT EXISTS ix_items_pushed_at ON items (pushed_at)",
        "ALTER TABLE categories ADD COLUMN IF NOT EXISTS group_name VARCHAR(100)",
    ]
    for sql in migrations:
        try:
            await conn.execute(text(sql))
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _migrate_columns(conn)
    yield


PUBLIC_READ_ONLY = os.getenv("PUBLIC_READ_ONLY", "false").lower() == "true"

app = FastAPI(
    title="FeedWire",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if PUBLIC_READ_ONLY else "/docs",
    redoc_url=None if PUBLIC_READ_ONLY else "/redoc",
    openapi_url=None if PUBLIC_READ_ONLY else "/openapi.json",
)


@app.middleware("http")
async def public_showcase_is_read_only(request, call_next):
    if PUBLIC_READ_ONLY and request.url.path.startswith("/api/"):
        path = request.url.path
        public_reads = (
            path in {
                "/api/health", "/api/feeds", "/api/categories", "/api/items",
                "/api/items/count", "/api/items/unread-counts", "/api/items/clusters",
                "/api/tags",
            }
            or path.startswith("/api/items/") and path.rsplit("/", 1)[-1].isdigit()
            or path.endswith("/readable") and path.startswith("/api/items/")
        )
        if request.method != "GET" or not public_reads:
            return JSONResponse({"detail": "Not found"}, status_code=404)
    return await call_next(request)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(feeds.router)
app.include_router(items.router)
app.include_router(categories.router)
app.include_router(rules.router)
app.include_router(notes.router)
app.include_router(ai.router)
app.include_router(settings.router)
app.include_router(digest.router)
app.include_router(tags.router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "app": "FeedWire"}

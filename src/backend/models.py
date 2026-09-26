from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey,
    JSON, UniqueConstraint, Index, Float, Table
)
from sqlalchemy.orm import relationship, DeclarativeBase
from datetime import datetime, timezone


def utcnow():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


item_tags = Table(
    "item_tags",
    Base.metadata,
    Column("item_id", Integer, ForeignKey("items.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    color = Column(String(7), default="#6366f1")
    created_at = Column(DateTime(timezone=True), default=utcnow)

    items = relationship("Item", secondary=item_tags, back_populates="tags")


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    group_name = Column(String(100), nullable=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    feeds = relationship("Feed", back_populates="category")


class Feed(Base):
    __tablename__ = "feeds"

    id = Column(Integer, primary_key=True)
    url = Column(String(2048), nullable=False, unique=True)
    title = Column(String(500))
    description = Column(Text)
    site_url = Column(String(2048))
    favicon_url = Column(String(2048))
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    is_private = Column(Boolean, default=False)
    title_custom = Column(Boolean, default=False)
    fetch_interval_minutes = Column(Integer, default=30)
    last_fetched_at = Column(DateTime(timezone=True))
    last_error = Column(Text)
    error_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    category = relationship("Category", back_populates="feeds")
    items = relationship("Item", back_populates="feed", cascade="all, delete-orphan")


class Item(Base):
    __tablename__ = "items"
    __table_args__ = (
        UniqueConstraint("feed_id", "guid", name="uq_feed_guid"),
        Index("ix_items_published", "published_at"),
        Index("ix_items_feed_published", "feed_id", "published_at"),
    )

    id = Column(Integer, primary_key=True)
    feed_id = Column(Integer, ForeignKey("feeds.id"), nullable=False)
    guid = Column(String(2048))
    title = Column(String(1000))
    link = Column(String(2048))
    content = Column(Text)
    author = Column(String(500))
    published_at = Column(DateTime(timezone=True))
    ai_summary = Column(Text)
    ai_entities = Column(JSON)
    cleaned_content = Column(Text)
    is_read = Column(Boolean, default=False, index=True)
    is_saved = Column(Boolean, default=False, index=True)
    is_hidden = Column(Boolean, default=False, index=True)
    matched_rules = Column(JSON, default=list)
    cluster_id = Column(String(100), index=True)
    dedup_hash = Column(String(64), index=True)
    relevance_score = Column(Float, default=0.0, index=True)
    feedback = Column(Integer, default=0, index=True)  # -1 down, 0 none, 1 up
    pushed_at = Column(DateTime(timezone=True), index=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    feed = relationship("Feed", back_populates="items")
    notes = relationship("Note", back_populates="item", cascade="all, delete-orphan")
    tags = relationship("Tag", secondary=item_tags, back_populates="items")


class Rule(Base):
    __tablename__ = "rules"

    id = Column(Integer, primary_key=True)
    name = Column(String(200))
    match_expression = Column(String(1000), nullable=False)
    scope = Column(String(50), default="title")
    match_whole_word = Column(Boolean, default=False)
    category_ids = Column(JSON, default=list)
    actions = Column(JSON, default=list)
    is_active = Column(Boolean, default=True)
    background_enabled = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)


class Note(Base):
    __tablename__ = "notes"

    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=True)
    title = Column(String(500))
    content = Column(Text)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    item = relationship("Item", back_populates="notes")


class UserAction(Base):
    __tablename__ = "user_actions"

    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    action = Column(String(50), nullable=False)  # read, save, click, summarize
    feed_id = Column(Integer)
    keywords = Column(JSON, default=list)
    created_at = Column(DateTime(timezone=True), default=utcnow)


class SyntheticFeed(Base):
    __tablename__ = "synthetic_feeds"

    id = Column(Integer, primary_key=True)
    page_url = Column(String(2048), nullable=False, unique=True)
    selector = Column(String(500))
    feed_id = Column(Integer, ForeignKey("feeds.id"), nullable=True)
    last_checked_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=utcnow)


class Setting(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True)
    key = Column(String(200), nullable=False, unique=True)
    value = Column(Text)

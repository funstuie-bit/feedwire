from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class CategoryCreate(BaseModel):
    name: str
    sort_order: int = 0
    group_name: Optional[str] = None

class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    sort_order: Optional[int] = None
    group_name: Optional[str] = None

class CategoryOut(BaseModel):
    id: int
    name: str
    sort_order: int
    group_name: Optional[str] = None
    feed_count: int = 0
    unread_count: int = 0
    model_config = {"from_attributes": True}


class FeedCreate(BaseModel):
    url: str
    category_id: Optional[int] = None
    is_private: bool = False
    fetch_interval_minutes: int = 30
    is_synthetic: bool = False

class FeedOut(BaseModel):
    id: int
    url: str
    title: Optional[str]
    description: Optional[str]
    site_url: Optional[str]
    favicon_url: Optional[str]
    category_id: Optional[int]
    is_private: bool
    fetch_interval_minutes: int
    last_fetched_at: Optional[datetime]
    last_error: Optional[str]
    error_count: int
    item_count: int = 0
    unread_count: int = 0
    created_at: datetime
    model_config = {"from_attributes": True}


class SimilarItem(BaseModel):
    id: int
    feed_title: Optional[str] = None
    feed_id: int
    link: Optional[str] = None

class TagOut(BaseModel):
    id: int
    name: str
    color: str = "#6366f1"
    model_config = {"from_attributes": True}

class TagCreate(BaseModel):
    name: str
    color: str = "#6366f1"


class ItemOut(BaseModel):
    id: int
    feed_id: int
    guid: Optional[str]
    title: Optional[str]
    link: Optional[str]
    content: Optional[str]
    cleaned_content: Optional[str] = None
    author: Optional[str]
    published_at: Optional[datetime]
    ai_summary: Optional[str]
    ai_entities: Optional[dict]
    is_read: bool
    is_saved: bool
    is_hidden: bool = False
    tags: list[TagOut] = []
    matched_rules: list = []
    cluster_id: Optional[str] = None
    relevance_score: float = 0.0
    feedback: int = 0
    similar_items: list[SimilarItem] = []
    is_paywalled: bool = False
    archive_url: Optional[str] = None
    feed_title: Optional[str] = None
    feed_favicon: Optional[str] = None
    created_at: datetime
    model_config = {"from_attributes": True}

class ItemUpdate(BaseModel):
    is_read: Optional[bool] = None
    is_saved: Optional[bool] = None
    is_hidden: Optional[bool] = None
    feedback: Optional[int] = None  # -1, 0, 1

class BulkItemUpdate(BaseModel):
    item_ids: list[int]
    is_read: Optional[bool] = None
    is_saved: Optional[bool] = None


class RuleCreate(BaseModel):
    name: Optional[str] = None
    match_expression: str
    scope: str = "title"
    match_whole_word: bool = False
    category_ids: list[int] = []
    actions: list[str] = []
    is_active: bool = True
    background_enabled: bool = False

class RuleOut(BaseModel):
    id: int
    name: Optional[str]
    match_expression: str
    scope: str
    match_whole_word: bool
    category_ids: list[int]
    actions: list[str]
    is_active: bool
    background_enabled: bool
    created_at: datetime
    model_config = {"from_attributes": True}


class NoteCreate(BaseModel):
    item_id: Optional[int] = None
    title: Optional[str] = None
    content: str

class NoteOut(BaseModel):
    id: int
    item_id: Optional[int]
    title: Optional[str]
    content: str
    item_title: Optional[str] = None
    created_at: datetime
    model_config = {"from_attributes": True}


class SettingUpdate(BaseModel):
    key: str
    value: str = ""

class SettingsOut(BaseModel):
    settings: dict[str, str]


class AIRequest(BaseModel):
    item_id: int
    action: str

class OPMLImport(BaseModel):
    content: str

class SyntheticFeedCreate(BaseModel):
    page_url: str
    category_id: Optional[int] = None

class ClusterOut(BaseModel):
    cluster_id: str
    label: str
    size: int
    item_ids: list[int]

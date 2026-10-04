"""Small local headline embeddings; no article text or API calls leave the app."""
import logging
import os
from collections import OrderedDict
from functools import lru_cache
from threading import Lock

MODEL = "sentence-transformers/all-MiniLM-L6-v2"
logger = logging.getLogger(__name__)
_cache = OrderedDict()
_lock = Lock()


@lru_cache(maxsize=1)
def _model():
    try:
        from fastembed import TextEmbedding
        return TextEmbedding(model_name=MODEL, threads=2,
                             cache_dir=os.getenv("FASTEMBED_CACHE_PATH", "/opt/feedwire-models"),
                             local_files_only=True)
    except Exception:
        logger.warning("Local headline model unavailable; using URL/headline matching")
        return None


def embeddings_for_items(items):
    if len(items) < 2:
        return {}
    with _lock:
        model = _model()
        if model is None:
            return {}
        titles = {item.id: (item.title or "").strip()[:1000] for item in items if item.title}
        missing = list(dict.fromkeys(title for title in titles.values() if title not in _cache))
        try:
            if missing:
                for title, vector in zip(missing, model.embed(missing, batch_size=64)):
                    _cache[title] = vector
            result = {id: _cache[title] for id, title in titles.items()}
            for title in titles.values():
                _cache.move_to_end(title)
            while len(_cache) > 4096:
                _cache.popitem(last=False)
            return result
        except Exception:
            logger.warning("Local headline embedding failed; using URL/headline matching", exc_info=True)
            return {}

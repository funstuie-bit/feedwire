import re
import hashlib
from difflib import SequenceMatcher
from collections import defaultdict
from models import Item
from urllib.parse import urlsplit, parse_qsl, urlencode
from datetime import timedelta


def canonical_article_url(url: str | None) -> str:
    """Ignore tracking/fragments, retaining query values that identify articles."""
    try:
        parsed = urlsplit(url or "")
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return ""
        query = sorted((k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
                       if not k.lower().startswith("utm_") and k.lower() not in ("fbclid", "gclid"))
        path = parsed.path.rstrip("/")
        # A publisher homepage is not an article identity.
        if not path and not query:
            return ""
        return parsed.netloc.lower().removeprefix("www.") + path + ("?" + urlencode(query) if query else "")
    except ValueError:
        return ""


def same_story(a: Item, b: Item, threshold: float) -> bool:
    link_a, link_b = canonical_article_url(a.link), canonical_article_url(b.link)
    if link_a and link_a == link_b:
        return True
    if a.feed_id == b.feed_id:
        return False
    date_a, date_b = a.published_at or a.created_at, b.published_at or b.created_at
    if date_a and date_b and abs(date_a - date_b) > timedelta(hours=48):
        return False
    if title_similarity(a.title or "", b.title or "") >= threshold:
        return True
    # A short headline can be wholly contained in another outlet's longer one.
    # Require six substantive shared words; do not collapse generic short titles.
    stop = {"a", "an", "the", "and", "or", "to", "of", "in", "on", "for", "with", "by", "at", "as", "is"}
    wa = set(normalize_title(a.title or "").split()) - stop
    wb = set(normalize_title(b.title or "").split()) - stop
    shorter, longer = sorted((wa, wb), key=len)
    nums_a, nums_b = {w for w in wa if w.isdigit()}, {w for w in wb if w.isdigit()}
    return (len(shorter) >= 6 and len(shorter & longer) / len(shorter) >= 0.9
            and not (nums_a and nums_b and nums_a != nums_b))


def normalize_title(title: str) -> str:
    if not title:
        return ""
    t = title.lower().strip()
    t = re.sub(r'[^\w\s]', '', t)
    t = re.sub(r'\s+', ' ', t)
    # Remove common prefixes like "Breaking:", "Update:", etc.
    t = re.sub(r'^(breaking|update|exclusive|opinion|analysis|review)\s*:?\s*', '', t)
    return t.strip()


def compute_dedup_hash(title: str) -> str:
    normalized = normalize_title(title)
    words = sorted(set(normalized.split()))
    return hashlib.md5(" ".join(words).encode()).hexdigest()[:16]


def title_similarity(a: str, b: str) -> float:
    na = normalize_title(a)
    nb = normalize_title(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def find_duplicates(items: list[Item], threshold: float = 0.75) -> dict[int, list[int]]:
    """Returns a dict mapping primary item IDs to lists of duplicate item IDs."""
    groups: dict[int, list[int]] = {}
    used: set[int] = set()
    rank = {item.id: index for index, item in enumerate(items)}

    # The concise headline is the anchor for expanded versions. Select anchors
    # independently of query sort order, then keep the first input item as the
    # displayed representative so newest/relevance ordering is preserved.
    for item_a in sorted(items, key=lambda item: len(normalize_title(item.title or ""))):
        if item_a.id in used:
            continue

        duplicates = []
        for item_b in items:
            if item_a.id == item_b.id or item_b.id in used:
                continue
            if same_story(item_a, item_b, threshold):
                duplicates.append(item_b.id)
                used.add(item_b.id)

        if duplicates:
            members = sorted([item_a.id, *duplicates], key=rank.__getitem__)
            groups[members[0]] = members[1:]
            used.add(item_a.id)

    return groups


def group_items_with_dedup(items: list[Item], threshold: float = 0.75) -> list[dict]:
    """Returns items with duplicate grouping metadata."""
    dupes = find_duplicates(items, threshold)
    dupe_children = set()
    for children in dupes.values():
        dupe_children.update(children)

    item_map = {item.id: item for item in items}
    result = []

    for item in items:
        if item.id in dupe_children:
            continue

        entry = {"item": item, "similar_items": []}
        if item.id in dupes:
            for child_id in dupes[item.id]:
                if child_id in item_map:
                    child = item_map[child_id]
                    entry["similar_items"].append({
                        "id": child.id,
                        "feed_title": None,  # filled by caller
                        "feed_id": child.feed_id,
                        "link": child.link,
                    })
        result.append(entry)

    return result

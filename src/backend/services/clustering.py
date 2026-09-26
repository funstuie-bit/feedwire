import re
import hashlib
from collections import defaultdict, Counter
from models import Item


STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "shall", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "as", "into", "through", "during",
    "before", "after", "above", "below", "between", "out", "off", "over",
    "under", "again", "further", "then", "once", "here", "there", "when",
    "where", "why", "how", "all", "both", "each", "few", "more", "most",
    "other", "some", "such", "no", "nor", "not", "only", "own", "same",
    "so", "than", "too", "very", "just", "but", "and", "or", "if", "its",
    "it", "this", "that", "these", "those", "what", "which", "who", "whom",
    "his", "her", "he", "she", "they", "them", "their", "we", "our", "you",
    "your", "my", "me", "up", "about", "new", "says", "said", "also",
    "get", "gets", "got", "like", "one", "two", "first", "last", "now",
    "going", "still", "back", "even", "much", "many", "well", "way",
}


def extract_keywords(title: str, min_length: int = 3) -> list[str]:
    if not title:
        return []
    words = re.findall(r'[a-z]+', title.lower())
    return [w for w in words if len(w) >= min_length and w not in STOP_WORDS]


def cluster_items(items: list[Item], min_cluster_size: int = 2) -> list[dict]:
    """Group items by shared keywords into topic clusters."""
    # Extract keywords for each item
    item_keywords: dict[int, set[str]] = {}
    keyword_items: dict[str, set[int]] = defaultdict(set)

    for item in items:
        kws = set(extract_keywords(item.title or ""))
        item_keywords[item.id] = kws
        for kw in kws:
            keyword_items[kw].add(item.id)

    # Find keyword pairs that co-occur frequently
    item_map = {item.id: item for item in items}
    assigned: set[int] = set()
    clusters: list[dict] = []

    # Sort keywords by frequency (most common first)
    sorted_keywords = sorted(keyword_items.items(), key=lambda x: -len(x[1]))

    for keyword, item_ids in sorted_keywords:
        # Only use keywords that appear in multiple items from different feeds
        unassigned = item_ids - assigned
        if len(unassigned) < min_cluster_size:
            continue

        # Check items are from different feeds
        feed_ids = set()
        cluster_items_list = []
        for iid in unassigned:
            if iid in item_map:
                feed_ids.add(item_map[iid].feed_id)
                cluster_items_list.append(iid)

        if len(feed_ids) < 2 and len(cluster_items_list) < 3:
            continue

        # Find the best label: most common shared keyword among these items
        shared_keywords = Counter()
        for iid in cluster_items_list:
            for kw in item_keywords.get(iid, set()):
                shared_keywords[kw] += 1

        # Pick top 2-3 keywords as the cluster label
        top_kws = [kw for kw, _ in shared_keywords.most_common(3) if shared_keywords[kw] >= min_cluster_size]
        if not top_kws:
            top_kws = [keyword]

        label = " / ".join(w.title() for w in top_kws[:3])
        cluster_id = hashlib.md5(label.encode()).hexdigest()[:12]

        clusters.append({
            "cluster_id": cluster_id,
            "label": label,
            "item_ids": cluster_items_list,
            "keyword": keyword,
            "size": len(cluster_items_list),
        })

        assigned.update(cluster_items_list)

    # Sort clusters by size
    clusters.sort(key=lambda c: -c["size"])

    return clusters


def assign_clusters(items: list[Item]) -> list[Item]:
    """Assign cluster_id to items in-place and return them."""
    clusters = cluster_items(items)

    for cluster in clusters:
        for item_id in cluster["item_ids"]:
            for item in items:
                if item.id == item_id:
                    item.cluster_id = cluster["cluster_id"]
                    break

    return items

import feedparser
import httpx
import os
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
import re
import hashlib


def _apply_reddit_auth(url: str) -> str:
    # Reddit started rejecting anonymous RSS in mid-2026. Authenticated feeds
    # work if you tack on the user= and feed= params from prefs/feeds. Same
    # token pair works for every Reddit URL, including /search/.rss.
    try:
        parsed = urlparse(url)
    except Exception:
        return url
    host = (parsed.hostname or "").lower()
    if not (host == "reddit.com" or host.endswith(".reddit.com")):
        return url
    user = (os.environ.get("REDDIT_RSS_USER") or "").strip()
    feed = (os.environ.get("REDDIT_RSS_FEED") or "").strip()
    # Defensive: a stray "&amp" or similar copy-paste artefact in the env value
    # would otherwise become part of the token and break auth.
    feed = re.split(r"[&?\s]", feed, 1)[0]
    if not user or not feed:
        return url
    query = [(k, v) for (k, v) in parse_qsl(parsed.query, keep_blank_values=True)
             if k not in ("user", "feed")]
    query.extend([("user", user), ("feed", feed)])
    return urlunparse(parsed._replace(query=urlencode(query)))


async def fetch_and_parse_feed(url: str) -> dict:
    url = _apply_reddit_auth(url)
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        headers = {"User-Agent": "FeedWire/1.0 (RSS Reader)"}
        response = await client.get(url, headers=headers)
        response.raise_for_status()

    feed = feedparser.parse(response.text)

    if feed.bozo and not feed.entries:
        raise ValueError(f"Failed to parse feed: {feed.bozo_exception}")

    feed_info = {
        "title": feed.feed.get("title", ""),
        "description": feed.feed.get("description", ""),
        "site_url": feed.feed.get("link", ""),
        "favicon_url": _extract_favicon(feed.feed.get("link", "")),
    }

    items = []
    for entry in feed.entries:
        content = ""
        if hasattr(entry, "content") and entry.content:
            content = entry.content[0].get("value", "")
        elif hasattr(entry, "summary"):
            content = entry.summary or ""

        published = _parse_date(entry)
        guid = entry.get("id") or entry.get("link") or _hash_entry(entry)

        items.append({
            "guid": guid,
            "title": entry.get("title", ""),
            "link": entry.get("link", ""),
            "content": content,
            "author": entry.get("author", ""),
            "published_at": published,
        })

    return {"feed": feed_info, "items": items}


def _parse_date(entry) -> Optional[datetime]:
    from time import mktime
    from datetime import timedelta
    # Allow a small clock-skew window; discard anything further in the future
    # since some feeds ship bad/placeholder dates that pin bogus items to the top.
    future_cutoff = datetime.now(timezone.utc) + timedelta(hours=1)
    for attr in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            try:
                dt = datetime.fromtimestamp(mktime(parsed), tz=timezone.utc)
            except (ValueError, OverflowError):
                continue
            if dt > future_cutoff:
                continue
            return dt
    return None


def _hash_entry(entry) -> str:
    raw = f"{entry.get('title', '')}{entry.get('link', '')}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _extract_favicon(site_url: str) -> Optional[str]:
    if not site_url:
        return None
    try:
        from urllib.parse import urlparse
        parsed = urlparse(site_url)
        return f"{parsed.scheme}://{parsed.netloc}/favicon.ico"
    except Exception:
        return None


async def discover_feed_url(page_url: str) -> Optional[str]:
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        headers = {"User-Agent": "FeedWire/1.0 (RSS Reader)"}
        response = await client.get(page_url, headers=headers)
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "lxml")

    for link in soup.find_all("link", rel="alternate"):
        link_type = link.get("type", "")
        if "rss" in link_type or "atom" in link_type or "xml" in link_type:
            href = link.get("href", "")
            if href:
                if href.startswith("/"):
                    from urllib.parse import urlparse
                    parsed = urlparse(page_url)
                    href = f"{parsed.scheme}://{parsed.netloc}{href}"
                return href

    return None


def parse_opml(content: str) -> list[dict]:
    feeds = []
    soup = BeautifulSoup(content, "lxml-xml")

    for outline in soup.find_all("outline"):
        xml_url = outline.get("xmlUrl")
        if xml_url:
            category = None
            parent = outline.parent
            if parent and parent.name == "outline":
                category = parent.get("text") or parent.get("title")

            feeds.append({
                "url": xml_url,
                "title": outline.get("title") or outline.get("text") or "",
                "category": category,
            })

    return feeds


def generate_opml(feeds: list[dict]) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<opml version="2.0">',
        "  <head>",
        "    <title>FeedWire Subscriptions</title>",
        "  </head>",
        "  <body>",
    ]

    by_category = {}
    for f in feeds:
        cat = f.get("category") or "Uncategorized"
        by_category.setdefault(cat, []).append(f)

    for cat, cat_feeds in sorted(by_category.items()):
        lines.append(f'    <outline text="{_xml_escape(cat)}">')
        for f in cat_feeds:
            title = _xml_escape(f.get("title", ""))
            url = _xml_escape(f.get("url", ""))
            site = _xml_escape(f.get("site_url", ""))
            lines.append(
                f'      <outline type="rss" text="{title}" title="{title}" '
                f'xmlUrl="{url}" htmlUrl="{site}"/>'
            )
        lines.append("    </outline>")

    lines.extend(["  </body>", "</opml>"])
    return "\n".join(lines)


def _xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )

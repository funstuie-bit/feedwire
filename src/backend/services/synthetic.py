import httpx
import hashlib
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse


async def create_synthetic_feed(page_url: str) -> dict:
    """Scrape a webpage and create a synthetic feed from its links/content."""
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        response = await client.get(
            page_url, headers={"User-Agent": "FeedWire/1.0 (RSS Reader)"}
        )
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "lxml")
    parsed_url = urlparse(page_url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"

    # Get page title
    page_title = soup.find("title")
    title = page_title.get_text(strip=True) if page_title else parsed_url.netloc

    # Find article-like links
    items = []
    seen_urls = set()

    # Look for links within article/content areas, or main content
    containers = (
        soup.find_all("article")
        or soup.find_all(class_=lambda c: c and any(
            x in (c if isinstance(c, str) else " ".join(c))
            for x in ["post", "article", "entry", "story", "item", "card"]
        ))
        or [soup.find("main") or soup.find("body")]
    )

    for container in containers:
        if not container:
            continue

        for link in container.find_all("a", href=True):
            href = link["href"]
            if not href or href.startswith("#") or href.startswith("javascript:"):
                continue

            # Make absolute
            full_url = urljoin(page_url, href)

            # Skip non-content links
            if any(x in full_url.lower() for x in [
                "/tag/", "/category/", "/author/", "/login", "/register",
                "/search", "/contact", "/about", "/privacy", "/terms",
                ".css", ".js", ".png", ".jpg", ".gif",
            ]):
                continue

            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            # Get link text
            link_text = link.get_text(strip=True)
            if not link_text or len(link_text) < 10 or len(link_text) > 300:
                continue

            # Skip navigation-like links
            if len(link_text.split()) < 3:
                continue

            # Get surrounding context
            parent = link.parent
            description = ""
            if parent:
                desc_el = parent.find(["p", "span", "div"], class_=lambda c: c and any(
                    x in (c if isinstance(c, str) else " ".join(c))
                    for x in ["desc", "summary", "excerpt", "snippet", "teaser"]
                ))
                if desc_el:
                    description = desc_el.get_text(strip=True)

            guid = hashlib.sha256(full_url.encode()).hexdigest()[:32]

            items.append({
                "guid": guid,
                "title": link_text,
                "link": full_url,
                "content": description,
                "author": "",
                "published_at": datetime.now(timezone.utc),
            })

    return {
        "feed": {
            "title": f"{title} (Synthetic)",
            "description": f"Synthetic feed created from {page_url}",
            "site_url": page_url,
            "favicon_url": f"{base_url}/favicon.ico",
        },
        "items": items[:50],  # Cap at 50 items
    }

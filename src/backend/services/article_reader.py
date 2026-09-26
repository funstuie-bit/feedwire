import httpx
from bs4 import BeautifulSoup


async def fetch_readable_content(url: str) -> str:
    """Fetch a URL and extract clean, readable article content."""
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(
                url, headers={"User-Agent": "FeedWire/1.0 (RSS Reader)"}
            )
            response.raise_for_status()

        return extract_article(response.text)
    except Exception:
        return ""


def extract_article(html: str) -> str:
    """Extract main article content from HTML, stripping chrome."""
    soup = BeautifulSoup(html, "lxml")

    # Remove unwanted elements
    for tag in soup.find_all([
        "nav", "header", "footer", "script", "style", "aside", "form",
        "iframe", "noscript", "svg",
    ]):
        tag.decompose()

    # Remove elements that are typically ads/banners
    for selector in [
        "[class*='cookie']", "[class*='banner']", "[class*='popup']",
        "[class*='modal']", "[class*='sidebar']", "[class*='social']",
        "[class*='share']", "[class*='comment']", "[class*='related']",
        "[class*='newsletter']", "[class*='subscribe']", "[class*='promo']",
        "[class*='advert']", "[class*='sponsor']", "[id*='cookie']",
        "[id*='banner']", "[id*='popup']", "[id*='modal']",
        "[id*='sidebar']", "[id*='comment']",
    ]:
        for el in soup.select(selector):
            el.decompose()

    # Try common article selectors (most specific first)
    article = (
        soup.find("article")
        or soup.find(class_="post-content")
        or soup.find(class_="entry-content")
        or soup.find(class_="article-body")
        or soup.find(class_="article-content")
        or soup.find(class_="story-body")
        or soup.find(class_="post-body")
        or soup.find(id="article-body")
        or soup.find(id="content")
        or soup.find("main")
    )

    if article:
        return _clean_text(article)

    # Fallback: find the largest block of paragraph text
    paragraphs = soup.find_all("p")
    blocks = []
    for p in paragraphs:
        text = p.get_text(strip=True)
        if len(text) > 40:
            blocks.append(text)

    if blocks:
        return " ".join(blocks)

    return soup.get_text(separator=" ", strip=True)[:8000]


def _clean_text(element) -> str:
    """Clean extracted article element into readable text."""
    # Remove remaining unwanted nested elements
    for tag in element.find_all(["button", "input", "select", "textarea"]):
        tag.decompose()

    lines = []
    for child in element.descendants:
        if child.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            lines.append(f"\n## {child.get_text(strip=True)}\n")
        elif child.name == "p":
            text = child.get_text(strip=True)
            if text:
                lines.append(text + "\n")
        elif child.name == "li":
            text = child.get_text(strip=True)
            if text:
                lines.append(f"  - {text}")
        elif child.name == "blockquote":
            text = child.get_text(strip=True)
            if text:
                lines.append(f"> {text}\n")

    if lines:
        return "\n".join(lines)

    return element.get_text(separator=" ", strip=True)


def create_reader_html(content: str) -> str:
    """Convert cleaned text back to simple, readable HTML."""
    if not content:
        return ""

    soup = BeautifulSoup(content, "lxml")

    # If it's already HTML, clean and return
    if soup.find():
        # Remove all attributes except href on links
        for tag in soup.find_all(True):
            allowed = {}
            if tag.name == "a" and tag.get("href"):
                allowed["href"] = tag["href"]
                allowed["target"] = "_blank"
                allowed["rel"] = "noopener noreferrer"
            if tag.name == "img" and tag.get("src"):
                allowed["src"] = tag["src"]
                allowed["alt"] = tag.get("alt", "")
                allowed["loading"] = "lazy"
            tag.attrs = allowed

        return str(soup)

    # Plain text — wrap in paragraphs
    paragraphs = content.split("\n\n")
    html_parts = []
    for p in paragraphs:
        p = p.strip()
        if p:
            if p.startswith("## "):
                html_parts.append(f"<h3>{p[3:]}</h3>")
            elif p.startswith("> "):
                html_parts.append(f"<blockquote>{p[2:]}</blockquote>")
            elif p.startswith("  - "):
                items = [line.strip("- ").strip() for line in p.split("\n") if line.strip()]
                html_parts.append("<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>")
            else:
                html_parts.append(f"<p>{p}</p>")

    return "\n".join(html_parts)

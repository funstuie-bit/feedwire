import re
from bs4 import BeautifulSoup


def _is_mostly_plain_text(html: str) -> bool:
    """Check if content is plain text with little/no HTML structure."""
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text()
    # If there are very few block-level tags relative to text length, it's plain text
    block_tags = soup.find_all(["p", "div", "h1", "h2", "h3", "h4", "ul", "ol", "blockquote", "pre"])
    if not block_tags and len(text) > 200:
        return True
    # If the ratio of text to tags is very high, treat as plain text
    if len(block_tags) < len(text) / 500 and len(text) > 300:
        return True
    return False


def _format_plain_text(text: str) -> str:
    """Convert plain text to readable HTML with paragraphs and structure."""
    # Normalise line endings
    text = text.replace('\r\n', '\n').replace('\r', '\n')

    # Split on double newlines for paragraphs
    blocks = re.split(r'\n{2,}', text)

    html_parts = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue

        # Detect markdown-style headings
        if block.startswith('## '):
            html_parts.append(f'<h3>{_escape(block[3:])}</h3>')
        elif block.startswith('# '):
            html_parts.append(f'<h2>{_escape(block[2:])}</h2>')
        # Detect list-like lines
        elif all(line.strip().startswith(('- ', '* ', '• ')) for line in block.split('\n') if line.strip()):
            items = []
            for line in block.split('\n'):
                line = line.strip()
                if line.startswith(('- ', '* ', '• ')):
                    items.append(f'<li>{_escape(line[2:])}</li>')
            html_parts.append(f'<ul>{"".join(items)}</ul>')
        # Detect code blocks
        elif block.startswith('```') or block.startswith('    '):
            code = block.strip('`').strip()
            html_parts.append(f'<pre><code>{_escape(code)}</code></pre>')
        else:
            # Regular paragraph — also handle single newlines within the block
            lines = block.split('\n')
            if len(lines) > 1:
                # Multiple single-spaced lines — join with <br>
                formatted = '<br>'.join(_escape(line) for line in lines)
                html_parts.append(f'<p>{formatted}</p>')
            else:
                html_parts.append(f'<p>{_escape(block)}</p>')

    return '\n'.join(html_parts)


def _escape(text: str) -> str:
    """Escape HTML entities but preserve existing inline elements."""
    return (
        text.replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
    )


def sanitize_content(html: str, item_link: str = "") -> str:
    """Clean up feed content HTML for safe, functional display."""
    if not html:
        return html

    # Check if this is mostly plain text that needs formatting
    if _is_mostly_plain_text(html):
        plain = BeautifulSoup(html, "lxml").get_text()
        return _format_plain_text(plain)

    soup = BeautifulSoup(html, "lxml")

    # Fix Twitter/RSSHub videos - replace with link to original tweet
    for video in soup.find_all("video"):
        poster = video.get("poster", "")
        link = item_link

        if poster:
            replacement = soup.new_tag("a", href=link, target="_blank", rel="noopener noreferrer")
            img = soup.new_tag("img", src=poster, loading="lazy", referrerpolicy="no-referrer")
            img["style"] = "max-width:100%;border-radius:8px;margin:0.5em 0;"
            replacement.append(img)
            caption = soup.new_tag("p")
            caption.string = "View video on X"
            caption["style"] = "font-size:12px;color:#656a76;margin-top:4px;"
            video.replace_with(replacement)
            replacement.insert_after(caption)
        else:
            replacement = soup.new_tag("a", href=link, target="_blank", rel="noopener noreferrer")
            replacement.string = "View video on X"
            replacement["style"] = "display:inline-block;padding:6px 12px;background:#1060ff;color:white;border-radius:5px;font-size:13px;text-decoration:none;margin:0.5em 0;"
            video.replace_with(replacement)

    # Fix images
    for img in soup.find_all("img"):
        img["referrerpolicy"] = "no-referrer"
        img["loading"] = "lazy"
        if "style" not in img.attrs:
            img["style"] = "max-width:100%;height:auto;border-radius:8px;margin:0.5em 0;"

    # Fix RSSHub quote blocks
    for div in soup.find_all("div", class_="rsshub-quote"):
        blockquote = soup.new_tag("blockquote")
        blockquote["style"] = "border-left:2px solid rgb(97,104,117);padding-left:12px;margin:0.75em 0;color:#656a76;"
        for child in list(div.children):
            blockquote.append(child.extract())
        div.replace_with(blockquote)

    body = soup.find("body")
    if body:
        return body.decode_contents()

    return str(soup)

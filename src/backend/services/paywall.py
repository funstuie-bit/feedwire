from urllib.parse import urlparse, quote

# Known paywalled domains
PAYWALLED_DOMAINS = {
    "nytimes.com", "wsj.com", "ft.com", "economist.com",
    "washingtonpost.com", "bloomberg.com", "thetimes.co.uk",
    "telegraph.co.uk", "theatlantic.com", "newyorker.com",
    "wired.com", "vanityfair.com", "hbr.org",
    "businessinsider.com", "insider.com", "seekingalpha.com",
    "barrons.com", "theathletic.com", "thedailybeast.com",
    "foreignpolicy.com", "foreignaffairs.com", "stratechery.com",
    "theinformation.com", "medium.com", "substack.com",
}

# Domains that sometimes have paywalls (metered)
METERED_DOMAINS = {
    "theguardian.com", "independent.co.uk", "bbc.com",
    "arstechnica.com", "reuters.com",
}


def is_paywalled(url: str) -> bool:
    if not url:
        return False
    try:
        domain = urlparse(url).netloc.lower()
        # Strip www.
        domain = domain.removeprefix("www.")
        return domain in PAYWALLED_DOMAINS
    except Exception:
        return False


def is_metered(url: str) -> bool:
    if not url:
        return False
    try:
        domain = urlparse(url).netloc.lower().removeprefix("www.")
        return domain in METERED_DOMAINS
    except Exception:
        return False


def get_archive_url(url: str) -> str:
    return f"https://archive.ph/newest/{quote(url, safe='')}"

"""Web: small helpers for links."""
import httpx


def follow(link: str) -> str:
    """Where a link ends up. Search results come back as temporary redirect links, so save the real one."""
    try:
        return str(httpx.head(link, follow_redirects=True, timeout=10).url)
    except httpx.HTTPError:
        return link

"""Web: follow a link, tell the team."""
import os

import httpx


def follow(link: str) -> str:
    """Where a link ends up. Search results come back as temporary redirect links, so save the real one."""
    try:
        return str(httpx.head(link, follow_redirects=True, timeout=10).url)
    except httpx.HTTPError:
        return link


def notify(text: str) -> bool:
    """Post a message to the team's Slack channel, if SLACK_WEBHOOK_URL is set. Returns whether it was sent."""
    url = os.environ.get("SLACK_WEBHOOK_URL")
    if not url:
        return False
    httpx.post(url, json={"text": text}, timeout=10).raise_for_status()
    return True

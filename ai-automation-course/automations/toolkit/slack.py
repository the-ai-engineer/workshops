"""Slack: post a message to the team's channel through an incoming webhook.

The webhook address is a secret. On Cloud Run it comes from Secret Manager.
"""
import os

import httpx

from toolkit import retry, shadow


def post(text: str) -> bool:
    """Post to Slack. Returns whether it was sent: shadow mode sends nothing."""
    if shadow.skip("post to Slack", text):
        return False
    url = os.environ["SLACK_WEBHOOK_URL"]
    retry.call(lambda: httpx.post(url, json={"text": text}, timeout=10).raise_for_status())
    return True

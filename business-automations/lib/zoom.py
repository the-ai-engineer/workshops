"""Zoom webhooks: check they really come from Zoom, and download a meeting's transcript.

In the Zoom app marketplace, make a webhook-only app, subscribe it to
"Recording transcript files have completed", turn on "include download token",
and copy its secret token to ZOOM_WEBHOOK_SECRET.
"""
import hashlib
import hmac
import os
import re

import httpx


def _sign(message: str) -> str:
    return hmac.new(os.environ["ZOOM_WEBHOOK_SECRET"].encode(), message.encode(), hashlib.sha256).hexdigest()


def is_genuine(body: bytes, timestamp: str, signature: str) -> bool:
    expected = "v0=" + _sign(f"v0:{timestamp}:{body.decode()}")
    return hmac.compare_digest(expected, signature)


def url_validation(plain_token: str) -> dict:
    """Zoom checks a new webhook URL by sending a token it expects back, signed."""
    return {"plainToken": plain_token, "encryptedToken": _sign(plain_token)}


def transcript(event: dict) -> str:
    """The transcript of a recording.transcript_completed event, as plain text with speaker names."""
    files = event["payload"]["object"]["recording_files"]
    url = next(f["download_url"] for f in files if f["file_type"] == "TRANSCRIPT")
    response = httpx.get(url, headers={"Authorization": f"Bearer {event['download_token']}"},
                         follow_redirects=True, timeout=60)
    response.raise_for_status()
    return vtt_to_text(response.text)


def vtt_to_text(vtt: str) -> str:
    """Drop the WEBVTT header, cue numbers and timestamps, keep the lines people said."""
    lines = []
    for line in vtt.splitlines():
        line = line.strip()
        if not line or line == "WEBVTT" or line.isdigit() or re.match(r"^\d\d:\d\d:\d\d\.\d+ -->", line):
            continue
        lines.append(line)
    return "\n".join(lines)

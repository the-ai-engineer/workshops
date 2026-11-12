"""Retry: try a call again when the failure is temporary, waiting longer each time.

Only temporary failures are retried: a dropped connection, "too many requests"
(429) or a server error (5xx). A bad request fails at once, because sending it
again won't fix it.
"""
import random
import time

import httpx

TEMPORARY = {429, 500, 502, 503, 504}


def _temporary(error: Exception) -> bool:
    if isinstance(error, httpx.TransportError):
        return True
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code in TEMPORARY
    # Google's libraries put the HTTP status in one of these attributes.
    status = getattr(error, "code", None) or getattr(getattr(error, "resp", None), "status", None)
    return isinstance(status, int) and status in TEMPORARY


def call(fn, attempts: int = 4, wait: float = 1.0):
    """Run fn(). On a temporary failure wait 1s, 2s, 4s (plus a little random), then try again."""
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as error:
            if attempt == attempts or not _temporary(error):
                raise
            time.sleep(wait * 2 ** (attempt - 1) + random.random() * wait)

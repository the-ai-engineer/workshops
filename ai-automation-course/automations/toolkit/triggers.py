"""Triggers: how an automation starts. The automation itself is a function called run.

    triggers.job(run)                         by hand, or on a schedule
    triggers.webhook(run)                     another system calls a URL, with a shared token
    triggers.webhook(run, check="signature")  the same, with a signed request

Every run writes one log line: what ran, whether it worked, how long it took,
the tokens it used and what it did. A failure writes an ERROR line, and one
alert rule (alerts.sh) watches for those.
"""
import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from toolkit import ai, shadow

NAME = Path(sys.argv[0]).stem  # the file that was run, e.g. 05_speed_to_lead
MAX_AGE = 300  # seconds a signed request stays valid


def _log(severity: str, **fields) -> None:
    print(json.dumps({"severity": severity, "automation": NAME, **fields}, default=str), flush=True)


def _timed(run, *args):
    ai.tokens = 0
    start = time.monotonic()
    result = run(*args)
    return result, {"seconds": round(time.monotonic() - start, 2), "tokens": ai.tokens, "shadow": shadow.on()}


def job(run) -> None:
    """Run once and stop. You start it by hand, or Cloud Scheduler starts it on a timer."""
    try:
        result, stats = _timed(run)
    except Exception as error:
        _log("ERROR", status="failed", error=repr(error))
        raise  # the run is marked as failed
    _log("INFO", status="ok", **stats, result=result)


# Signatures, the way Stripe and Slack do it. The caller hashes the timestamp and
# the exact body with a secret only you and it know. You do the same sum and
# compare. A match proves who sent it and that nobody changed it on the way. The
# timestamp stops an old request being sent again later.

def sign(body: bytes, secret: str, timestamp: int | None = None) -> str:
    """The X-Signature header for a body. Callers use this; so do the tests."""
    timestamp = int(time.time()) if timestamp is None else timestamp
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


def signature_ok(body: bytes, header: str, secret: str) -> bool:
    try:
        parts = dict(part.split("=", 1) for part in header.split(","))
        timestamp = int(parts["t"])
    except (KeyError, ValueError):
        return False
    if abs(time.time() - timestamp) > MAX_AGE:
        return False
    return hmac.compare_digest(sign(body, secret, timestamp), header)


def token_ok(token: str) -> bool:
    # compare_digest takes the same time whether a guess is close or not.
    return hmac.compare_digest(token.encode(), os.environ["WEBHOOK_TOKEN"].encode())


def webhook_app(run, check: str = "token") -> FastAPI:
    app = FastAPI()

    @app.post("/hook")
    async def hook(request: Request) -> dict:
        body = await request.body()  # the raw bytes: check them before parsing, which changes them

        # 1. Who is calling? Reject before any work, or any model call, happens.
        if check == "signature":
            allowed = signature_ok(body, request.headers.get("x-signature", ""), os.environ["WEBHOOK_SECRET"])
        else:
            allowed = token_ok(request.headers.get("x-token", ""))
        if not allowed:
            _log("WARNING", status="rejected", reason=f"bad {check}")
            raise HTTPException(401, f"bad {check}")

        # 2. Run it.
        try:
            payload = json.loads(body or b"{}")
            result, stats = await run_in_threadpool(_timed, run, payload)
        except (KeyError, ValueError) as error:  # the caller sent something the automation can't use
            _log("WARNING", status="bad request", error=str(error))
            raise HTTPException(400, f"bad request: {error}")
        except Exception as error:
            _log("ERROR", status="failed", error=repr(error))
            raise HTTPException(500, "failed")  # the caller can try again
        _log("INFO", status="ok", **stats, result=result)
        return result

    return app


def webhook(run, check: str = "token") -> None:
    """Wait for requests. Another system starts a run by sending a POST to /hook."""
    uvicorn.run(webhook_app(run, check), host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))  # Cloud Run sets PORT

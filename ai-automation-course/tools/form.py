"""A website enquiry form for the speed to lead demo.

The page is the client's website. This file is the website's backend: it signs
each enquiry with WEBHOOK_SECRET and sends it to the webhook, the way a real
site would. The secret stays here. It never reaches the browser.

    uv run python tools/form.py http://localhost:8080
    uv run python tools/form.py https://speed-to-lead-xxxx.a.run.app

Then open http://127.0.0.1:8770. Reads WEBHOOK_SECRET from .env.

    --private   also sign in to Google as you. Use it when the service isn't public,
                for example when your Google organisation blocks public URLs
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import uvicorn
from dotenv import load_dotenv
from fastapi import Body, FastAPI
from fastapi.responses import HTMLResponse

sys.path.insert(0, str(Path(__file__).parents[1] / "automations"))
from toolkit.triggers import sign  # noqa: E402

load_dotenv()
parser = argparse.ArgumentParser(description="A website enquiry form that calls the speed to lead webhook.")
parser.add_argument("url", nargs="?", default="http://localhost:8080")
parser.add_argument("--private", action="store_true")
args = parser.parse_args()
HOOK = args.url.rstrip("/") + "/hook"
PORT = 8770

app = FastAPI()


@app.get("/", response_class=HTMLResponse)
def page() -> str:
    return (Path(__file__).parent / "form.html").read_text()


@app.get("/defaults")
def defaults() -> dict:
    """Fills in your own address, so the proposal comes to you."""
    return {"email": os.environ.get("TEST_LEAD_EMAIL", ""), "webhook": HOOK}


@app.post("/send")
def send(enquiry: dict = Body(...)) -> dict:
    """What a website's backend does with a form: sign it, then pass it on."""
    body = json.dumps(enquiry).encode()
    headers = {"Content-Type": "application/json", "X-Signature": sign(body, os.environ["WEBHOOK_SECRET"])}
    if args.private:  # Google checks who is calling before the request reaches the webhook
        identity = subprocess.run(["gcloud", "auth", "print-identity-token"], capture_output=True, text=True, check=True)
        headers["Authorization"] = f"Bearer {identity.stdout.strip()}"
    started = time.monotonic()
    try:
        reply = httpx.post(HOOK, content=body, headers=headers, timeout=60)
    except httpx.HTTPError as error:
        return {"code": 0, "seconds": 0, "reply": f"Could not reach {HOOK}: {error}"}
    try:
        answer = reply.json()
    except ValueError:
        answer = reply.text[:300]
    return {"code": reply.status_code, "seconds": round(time.monotonic() - started, 1), "reply": answer}


if __name__ == "__main__":
    if not os.environ.get("WEBHOOK_SECRET"):
        raise SystemExit("Set WEBHOOK_SECRET in .env. It must match the one the webhook was deployed with.")
    print(f"Open http://127.0.0.1:{PORT}  (enquiries go to {HOOK})")
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")

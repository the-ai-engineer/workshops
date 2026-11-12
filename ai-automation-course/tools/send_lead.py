"""Send a signed test enquiry to the speed to lead webhook, the way a website form would.

    uv run python tools/send_lead.py http://localhost:8080
    uv run python tools/send_lead.py https://speed-to-lead-xxxx.a.run.app

Reads WEBHOOK_SECRET from .env.

    --message "..."   send a different enquiry. The same email and message twice is a repeat,
                      and a repeat is skipped, so use this when you want a new lead
    --tamper          change the body after signing, and watch the webhook reject it
    --bad             leave out the email, and watch a bad form get a 400
    --private         also sign in to Google as you. Use it when the service isn't public,
                      for example when your Google organisation blocks public URLs
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parents[1] / "automations"))
from toolkit.triggers import sign  # noqa: E402

load_dotenv()
parser = argparse.ArgumentParser(description="Send a signed test enquiry to the speed to lead webhook.")
parser.add_argument("url")
parser.add_argument("--message", default="We run three warehouses and our team re-types every delivery note "
                                         "into our system. Can you help us automate that?")
parser.add_argument("--tamper", action="store_true")
parser.add_argument("--bad", action="store_true")
parser.add_argument("--private", action="store_true")
args = parser.parse_args()

lead = {
    "name": "Sam Price",
    "email": os.environ.get("TEST_LEAD_EMAIL") or "sam@example.com",
    "company": "Price Logistics",
    "message": args.message,
}
if args.bad:
    del lead["email"]
body = json.dumps(lead).encode()
headers = {"Content-Type": "application/json", "X-Signature": sign(body, os.environ["WEBHOOK_SECRET"])}
if args.tamper:
    body = body.replace(b"Sam", b"Eve")
if args.private:  # Google checks who is calling before the request reaches the webhook
    identity = subprocess.run(["gcloud", "auth", "print-identity-token"], capture_output=True, text=True, check=True)
    headers["Authorization"] = f"Bearer {identity.stdout.strip()}"
response = httpx.post(args.url.rstrip("/") + "/hook", content=body, headers=headers, timeout=60)
print(response.status_code, response.text)

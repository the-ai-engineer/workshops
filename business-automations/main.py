"""One Cloud Run service for every automation: POST /run/<name>.

Cloud Scheduler calls the timed ones, a CRM or form calls the others. Every
caller sends the X-Token header so strangers can't run them. Zoom can't send
custom headers, so it has its own route, POST /zoom, checked by Zoom's signature.
"""
import hmac
import json
import os

from dotenv import load_dotenv
from fastapi import BackgroundTasks, Body, FastAPI, Header, HTTPException, Request

from automations import client_folder, invoice_inbox, meeting_follow_up, meeting_reminders
from lib import zoom

load_dotenv()

AUTOMATIONS = {
    "invoice_inbox": invoice_inbox.run,
    "client_folder": client_folder.run,
    "meeting_reminders": meeting_reminders.run,
    "meeting_follow_up": meeting_follow_up.run,
}

app = FastAPI()


@app.get("/")
def health() -> dict:
    return {"automations": list(AUTOMATIONS)}


@app.post("/run/{name}")
def run(name: str, payload: dict = Body(default={}), x_token: str = Header(default="")) -> dict:
    if not hmac.compare_digest(x_token, os.environ["AUTOMATION_TOKEN"]):
        raise HTTPException(401, "bad token")
    if name not in AUTOMATIONS:
        raise HTTPException(404, f"no automation called {name}")
    print(f"run {name} {payload}")  # Cloud Run sends stdout to Cloud Logging
    result = AUTOMATIONS[name](payload)
    print(f"done {name} {result}")
    return result


@app.post("/zoom")
async def zoom_webhook(request: Request, background: BackgroundTasks) -> dict:
    body = await request.body()
    if not zoom.is_genuine(body, request.headers.get("x-zm-request-timestamp", ""),
                           request.headers.get("x-zm-signature", "")):
        raise HTTPException(401, "not from Zoom")
    event = json.loads(body)
    if event["event"] == "endpoint.url_validation":
        return zoom.url_validation(event["payload"]["plainToken"])
    if event["event"] == "recording.transcript_completed":
        # Zoom wants an answer within 3 seconds, so the follow-up runs after the reply.
        background.add_task(run_and_log, "meeting_follow_up", event)
    return {"ok": True}


def run_and_log(name: str, payload: dict) -> None:
    print(f"run {name}")
    print(f"done {name} {AUTOMATIONS[name](payload)}")

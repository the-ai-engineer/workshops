"""One Cloud Run service for every automation: POST /run/<name>.

Cloud Scheduler calls the timed ones, a CRM or form calls the others. Every
caller sends the X-Token header so strangers can't run them.
"""
import hmac
import os

from dotenv import load_dotenv
from fastapi import Body, FastAPI, Header, HTTPException

from automations import client_folder, invoice_inbox, meeting_reminders

load_dotenv()

AUTOMATIONS = {
    "invoice_inbox": invoice_inbox.run,
    "client_folder": client_folder.run,
    "meeting_reminders": meeting_reminders.run,
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

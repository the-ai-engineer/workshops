"""A small control panel for the examples: each automation drawn as a flow, with a Run button.

It runs on your own machine and does what you would do in a terminal. The
button on a job runs `gcloud run jobs execute`. The button on a webhook sends
the request. It only listens on your own machine, and it can only run the
jobs and webhooks listed below.

    uv run python ui/app.py        then open http://127.0.0.1:8765
"""
import json
import os
import re
import subprocess
import time
from pathlib import Path

import httpx
import uvicorn
from dotenv import load_dotenv
from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import HTMLResponse

HERE = Path(__file__).parent
load_dotenv(HERE.parent / ".env")

PROJECT = os.environ.get("PROJECT") or os.environ.get("CLOUDSDK_CORE_PROJECT", "")
REGION = os.environ.get("REGION", "europe-west2")
JOBS = {"example-hello", "example-03-job-leads", "example-05-receipts", "example-06-video-to-content"}
WEBHOOKS = {"example-hello-webhook", "example-04-speed-to-lead"}

app = FastAPI()


def gcloud(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gcloud", *args, "--project", PROJECT], capture_output=True, text=True, timeout=900)


@app.get("/", response_class=HTMLResponse)
def page() -> str:
    return (HERE / "index.html").read_text()


@app.get("/config")
def config() -> dict:
    """The project, and the links the page shows beside each flow."""
    sheet, receipts, videos = (os.environ.get(key, "") for key in ("SHEET_ID", "RECEIPTS_FOLDER_ID", "VIDEOS_FOLDER_ID"))
    return {
        "project": PROJECT,
        "region": REGION,
        "sheet": f"https://docs.google.com/spreadsheets/d/{sheet}/edit" if sheet else "",
        "receipts": f"https://drive.google.com/drive/folders/{receipts}" if receipts else "",
        "videos": f"https://drive.google.com/drive/folders/{videos}" if videos else "",
    }


@app.post("/run/job/{name}")
def run_job(name: str) -> dict:
    """The manual trigger: run a job and wait for it to finish."""
    if name not in JOBS:
        raise HTTPException(404, "no such job")
    command = ["run", "jobs", "execute", name, "--region", REGION, "--wait"]
    started = time.time()
    done = gcloud(*command)
    execution = re.search(r"Execution \[([\w-]+)\]", done.stdout + done.stderr)
    return {
        "ok": done.returncode == 0,
        "seconds": round(time.time() - started),
        "command": "gcloud " + " ".join(command),
        "execution": execution.group(1) if execution else "",  # the page asks for its logs next
        "output": [] if execution else (done.stderr or done.stdout).strip().splitlines()[-4:],
    }


@app.get("/logs/{execution}")
def logs(execution: str) -> list[str]:
    """What a run printed. Logs take a few seconds to arrive, so look a few times."""
    if not re.fullmatch(r"example-[\w-]+", execution):
        raise HTTPException(404, "no such run")
    query = f'resource.type="cloud_run_job" AND labels."run.googleapis.com/execution_name"="{execution}"'
    for _ in range(8):
        found = gcloud("logging", "read", query, "--freshness", "15m", "--order", "asc", "--format", "json").stdout
        lines = []
        for entry in json.loads(found or "[]"):
            text = entry.get("textPayload") or (json.dumps(entry["jsonPayload"]) if "jsonPayload" in entry else "")
            if text and "Container called exit" not in text and "Warning" not in text and "Output only" not in text:
                lines.append(text.rstrip())
        if lines:
            return lines
        time.sleep(4)
    return ["The run finished. Its log lines have not arrived yet."]


@app.post("/run/webhook/{name}")
def run_webhook(name: str, payload: dict = Body(default={})) -> dict:
    """The webhook trigger: send a request to the service, the way another system would."""
    if name not in WEBHOOKS:
        raise HTTPException(404, "no such webhook")
    url = gcloud("run", "services", "describe", name, "--region", REGION, "--format", "value(status.url)").stdout.strip()
    if not url:
        raise HTTPException(502, "could not find the service. Is it deployed, and is PROJECT set in .env?")
    # Signs in as you as well, for projects where the URL is not public. A public service ignores it.
    identity = subprocess.run(["gcloud", "auth", "print-identity-token"], capture_output=True, text=True).stdout.strip()
    started = time.time()
    reply = httpx.post(f"{url}/hook", json=payload, timeout=120,
                       headers={"X-Token": os.environ.get("WEBHOOK_TOKEN", ""), "Authorization": f"Bearer {identity}"})
    try:
        output = reply.json()
    except ValueError:
        output = reply.text[:500]
    return {
        "ok": reply.status_code == 200,
        "seconds": round(time.time() - started),
        "command": f"curl -X POST {url}/hook -H \"X-Token: $WEBHOOK_TOKEN\" -d '{json.dumps(payload)}'",
        "output": output,
    }


if __name__ == "__main__":
    if not PROJECT:
        raise SystemExit("Set PROJECT in .env to your Google Cloud project id.")
    port = int(os.environ.get("PORT", "8765"))
    print(f"Open http://127.0.0.1:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")

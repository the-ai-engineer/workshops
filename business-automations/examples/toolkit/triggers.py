"""Triggers: how an automation starts. The automation itself is a function called run."""
import hmac
import json
import os

import uvicorn
from fastapi import Body, FastAPI, Header, HTTPException


def job(run) -> None:
    """Run once and stop. You start it by hand, or Cloud Scheduler starts it on a timer."""
    try:
        result = run()
    except Exception as error:
        print(json.dumps({"severity": "ERROR", "error": str(error)}))  # one clear line to alert on
        raise  # the run is marked as failed
    print(json.dumps(result))  # one line per run: Cloud Run keeps it in the logs


def webhook_app(run) -> FastAPI:
    app = FastAPI()

    @app.post("/hook")
    def hook(payload: dict = Body(default={}), x_token: str = Header(default="")) -> dict:
        # The URL is public, so first check who is calling.
        if not hmac.compare_digest(x_token.encode(), os.environ["WEBHOOK_TOKEN"].encode()):
            raise HTTPException(401, "bad token")
        result = run(payload)
        print(json.dumps(result))
        return result

    return app


def webhook(run) -> None:
    """Wait for requests. Another system starts a run by sending a POST to /hook."""
    uvicorn.run(webhook_app(run), host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))  # Cloud Run sets PORT

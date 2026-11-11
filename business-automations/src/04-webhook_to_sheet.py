"""04: a webhook trigger. The hello world of automations.

Trigger: an HTTP request. A form, Stripe, a CRM or plain curl sends a POST to /hook.
Input:   the JSON body of the request, e.g. {"name": "Owain"}.
Steps:   check the caller's token, add a row to the Webhook tab, say hello.
Output:  a row in the CRM sheet and a JSON reply.

The other examples are jobs: they start, do the work and stop. This one is a
service: it waits for requests. The URL is public, so the first step is always
to check who is calling. Swap the middle step for anything in tools.py.

    uv run python src/04-webhook_to_sheet.py
    curl -X POST localhost:8080/hook -H "X-Token: $WEBHOOK_TOKEN" -H "Content-Type: application/json" -d '{"name": "Owain"}'
"""
import hmac
import json
import os
from datetime import datetime

import uvicorn
from fastapi import Body, FastAPI, Header, HTTPException

import tools

app = FastAPI()


@app.post("/hook")
def hook(payload: dict = Body(default={}), x_token: str = Header(default="")) -> dict:
    if not hmac.compare_digest(x_token.encode(), os.environ["WEBHOOK_TOKEN"].encode()):
        raise HTTPException(401, "bad token")

    name = str(payload.get("name", "world"))
    tools.add_row(os.environ["CLIENTS_SHEET_ID"], "Webhook",
                  [datetime.now().isoformat(timespec="seconds"), name, json.dumps(payload)])
    print(json.dumps({"event": "hook", "status": "done", "name": name}))  # one line per run, for the logs
    return {"message": f"Hello, {name}!"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))  # Cloud Run sets PORT

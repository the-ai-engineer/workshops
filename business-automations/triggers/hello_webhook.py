"""Hello world, as a webhook.

Example 3, webhook:  another system starts it by sending an HTTP request.
    curl -X POST $URL/hook -H "X-Token: $WEBHOOK_TOKEN" -H "Content-Type: application/json" -d '{"name": "Owain"}'

A job starts, does the work and stops. This is a service: it waits for
requests. The URL is public, so the first step is always to check who is
calling. Swap what run() does and the trigger still works.

    python triggers/hello_webhook.py
"""
import hmac
import json
import os

import uvicorn
from fastapi import Body, FastAPI, Header, HTTPException

app = FastAPI()


def run(payload: dict) -> dict:
    # The automation goes here. This one only says hello.
    return {"message": f"Hello, {payload.get('name', 'world')}!"}


@app.post("/hook")
def hook(payload: dict = Body(default={}), x_token: str = Header(default="")) -> dict:
    if not hmac.compare_digest(x_token.encode(), os.environ["WEBHOOK_TOKEN"].encode()):
        raise HTTPException(401, "bad token")
    result = run(payload)
    print(json.dumps(result))  # one line per run: Cloud Run keeps it in the logs
    return result


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))  # Cloud Run sets PORT

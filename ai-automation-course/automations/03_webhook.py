"""03: webhook. Hello world, started when another system calls a URL.

A webhook is a service: it waits for requests. Whatever the caller sends
arrives in run as the payload. The URL is on the internet, so the trigger checks
a shared token in the X-Token header before run is called. A wrong token gets a
401 and run never starts.

    On your laptop:   uv run python automations/03_webhook.py
                      curl -X POST localhost:8080/hook -H "X-Token: $WEBHOOK_TOKEN" -d '{"name": "Owain"}'

Compare this with 01. The automation is still a run function. Only the last
line changed.
"""
from toolkit import triggers


def run(payload: dict) -> dict:
    return {"message": f"Hello, {payload.get('name', 'world')}!"}


if __name__ == "__main__":
    triggers.webhook(run)

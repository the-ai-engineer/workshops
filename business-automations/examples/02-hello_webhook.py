"""02: hello world, as a webhook.

A webhook waits for another system to call it. Whatever that system sends
arrives in run as the payload.

    curl -X POST $URL/hook -H "X-Token: $WEBHOOK_TOKEN" -H "Content-Type: application/json" -d '{"name": "Owain"}'

Compare this with 01. The automation is still a run function. Only the last
line changed.

    uv run python examples/02-hello_webhook.py
"""
from toolkit import triggers


def run(payload: dict) -> dict:
    return {"message": f"Hello, {payload.get('name', 'world')}!"}


if __name__ == "__main__":
    triggers.webhook(run)

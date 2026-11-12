"""Shadow mode: do all the work, send nothing.

It is on unless SHADOW=false. Every step that reaches the outside world (an
email, a Slack message) asks shadow.skip first. In shadow mode that step logs
what it would have done and does nothing, so you can run an automation on real
data and read the logs before you switch it on.
"""
import json
import os


def on() -> bool:
    return os.environ.get("SHADOW", "true").lower() != "false"


def skip(action: str, detail) -> bool:
    """True when shadow mode is on, after logging what would have happened."""
    if not on():
        return False
    print(json.dumps({"severity": "INFO", "shadow": True, "would": action, "detail": detail}, default=str))
    return True

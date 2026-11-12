"""02: scheduled. The same kind of job, started by a clock.

Nothing in this file knows about the schedule. deploy.sh creates a Cloud
Scheduler entry that starts the job every 5 minutes. The trigger is how the job
is deployed, not how it is written.

    On your laptop:   uv run python automations/02_scheduled.py
    On Cloud Run:     it runs every 5 minutes. Read its logs with the command deploy.sh prints.
    To stop it:       gcloud scheduler jobs pause hello-every-5-minutes --location $REGION
"""
from datetime import datetime, timezone

from toolkit import triggers


def run() -> dict:
    return {"message": "Hello from the schedule", "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


if __name__ == "__main__":
    triggers.job(run)

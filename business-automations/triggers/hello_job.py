"""Hello world, as a job. One script, two triggers.

Example 1, manual:     you start it.
    gcloud run jobs execute example-hello --region europe-west2 --wait
Example 2, scheduled:  the clock starts it. Cloud Scheduler runs the same job every 5 minutes.

Nothing in this file knows which of the two happened. That is the point: the
trigger is part of how the job is deployed, and the logic is here. Swap what
run() does and both triggers still work.

    python triggers/hello_job.py
"""
import json
from datetime import datetime, timezone


def run() -> dict:
    # The automation goes here. This one only says hello.
    return {"message": "Hello, world!", "time": datetime.now(timezone.utc).isoformat(timespec="seconds")}


if __name__ == "__main__":
    print(json.dumps(run()))  # one line per run: Cloud Run keeps it in the logs

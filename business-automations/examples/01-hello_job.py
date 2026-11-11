"""01: hello world, as a job.

A job starts, does its work and stops. The same job covers two triggers:

    manual      you run it:           gcloud run jobs execute example-hello --wait
    scheduled   the clock runs it:    Cloud Scheduler starts it every 5 minutes

Nothing here knows which one happened. The trigger is how the job is deployed.
The automation is the run function.

    uv run python examples/01-hello_job.py
"""
from toolkit import triggers


def run() -> dict:
    return {"message": "Hello, world!"}


if __name__ == "__main__":
    triggers.job(run)

# Build Professional AI Automations

The code for the course. Business automations of the kind people build in n8n, written as short Python scripts that run on Google Cloud Run.

The course outline is [COURSE.md](COURSE.md).

## The idea

An automation is a function called `run`. The last line of the file picks what starts it.

```python
from toolkit import triggers

def run() -> dict:
    return {"message": "Hello, world!"}

if __name__ == "__main__":
    triggers.job(run)        # or: triggers.webhook(run)
```

A **job** starts, does its work and stops. You run it by hand, or a schedule runs it. A **webhook** waits for another system to call its URL.

## The examples

Everything is in [`examples/`](examples/). Each file is one automation.

| File | What it does | Trigger | AI |
|---|---|---|---|
| [`01-hello_job.py`](examples/01-hello_job.py) | Says hello | Manual, and every 5 minutes on a schedule | None |
| [`02-hello_webhook.py`](examples/02-hello_webhook.py) | Says hello to whoever calls it with the right token | Webhook | None |
| [`03-job_leads.py`](examples/03-job_leads.py) | Finds new job adverts and adds them to the `Job leads` tab of a sheet | Schedule, 9am | One model call |
| [`04-speed_to_lead.py`](examples/04-speed_to_lead.py) | Saves a website enquiry to the `Enquiries` tab with a personal reply already written, and tells the team in Slack | Webhook | One model call |
| [`05-receipts.py`](examples/05-receipts.py) | Reads each new receipt in a Drive folder and adds a row to the `Expenses` tab | Schedule, every 15 minutes | One model call |
| [`06-video_to_content.py`](examples/06-video_to_content.py) | Turns a new video in a Drive folder into the content drafts that suit it, in the `Content` tab | Schedule, every 15 minutes | An agent, on Google's ADK |

[`examples/toolkit/`](examples/toolkit/) is the shared code, five short files:

| File | What it gives you |
|---|---|
| `triggers.py` | `triggers.job(run)` and `triggers.webhook(run)` |
| `sheets.py` | `sheets.read(tab)` and `sheets.add(tab, row)` |
| `drive.py` | `drive.new_files(folder, ...)`, `drive.download(id)`, `drive.mark_done(id)` |
| `ai.py` | `ai.ask(prompt, ...)` for one model call, `ai.transcribe(recording)`, `ai.agent(...)` for an agent with tools |
| `web.py` | `web.follow(link)` and `web.notify(text)` for Slack |

There are no API keys. On Cloud Run everything signs in as a service account, including the model, which is Gemini on Vertex AI.

## Set up

1. Install [uv](https://docs.astral.sh/uv/) and the [gcloud CLI](https://cloud.google.com/sdk/docs/install). Create a Google Cloud project with billing on.
2. `cp .env.example .env`, and set `WEBHOOK_TOKEN` to any long random text.
3. Deploy. The first run takes about four minutes.

```
gcloud auth login
PROJECT=your-project-id ./deploy-examples.sh
```

The script builds one container, deploys every example, and prints a command to try each one. It also prints the email address of the service account it runs as.

4. For examples 03 to 06, create a Google Sheet with tabs called `Job leads`, `Enquiries`, `Expenses` and `Content`, and two Drive folders, one for receipts and one for videos. Share the sheet and both folders with the service account as Editor. Put their ids in `.env` and deploy again.

## Run

```
gcloud run jobs execute example-hello --region europe-west2 --wait
gcloud run jobs execute example-03-job-leads --region europe-west2 --wait
gcloud run jobs execute example-05-receipts --region europe-west2 --wait
gcloud run jobs execute example-06-video-to-content --region europe-west2 --wait
```

The two webhooks are called with `curl`. The deploy script prints the exact commands.

To be emailed when any run fails:

```
PROJECT=your-project-id ALERT_EMAIL=you@example.com ./alerts.sh
```

## A control panel

[`ui/`](ui/) is a small page that draws each automation as a flow with a Run button, the way a no-code tool would. It runs on your own machine. A button on a job runs `gcloud run jobs execute`, and a button on a webhook sends the request.

```
uv run python ui/app.py
```

Then open http://127.0.0.1:8765. Set `PROJECT` in `.env` first.

## Test

```
uv sync
uv run pytest
```

The tests use a fake sheet, a fake Drive folder and a fake model, so they need no Google account.

## Add your own

Copy the example closest to what you need, change what `run` does, and add one line for it at the bottom of `deploy-examples.sh`. Use a model for a step that needs judgement, such as reading, writing or searching. Use plain code for everything else.

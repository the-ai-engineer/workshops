# Business automations

Replace typical n8n workflows with short Python scripts on Cloud Run. Write-up and run of show: [Business automations workshop](https://docs.google.com/document/d/1ISDKj-E8gQt2X-PPXvds_KcveNmbQh35LJdjSzg5ZRY/edit).

Most n8n workflows are a trigger, then a few fixed steps: fetch something, maybe one AI call, write it somewhere. That is a Python function. Cloud Run hosts it, Cloud Scheduler or a webhook triggers it, and Claude handles the one step that needs judgment.

## What's here

| Automation | Trigger | What it does |
|---|---|---|
| [`invoice_inbox`](automations/invoice_inbox.py) | Cloud Scheduler, every 5 minutes | A PDF dropped in the Inbox folder in Drive becomes a row in the Invoices sheet (Claude reads it), then moves to Processed |
| [`client_folder`](automations/client_folder.py) | Webhook from your CRM or form | A new client gets a Drive folder with subfolders, and a row in the Clients sheet |
| [`meeting_reminders`](automations/meeting_reminders.py) | Cloud Scheduler, 8am daily | Every guest from outside the business gets a reminder email the day before |

```
main.py          one service, POST /run/<name>, protected by the X-Token header
automations/     one file per automation, each a run(payload) function
lib/             google.py (Drive, Sheets, Calendar), ai.py (one typed Claude call), mail.py (SMTP)
tests/           every automation against fakes, no keys needed
deploy.sh        Cloud Run plus the scheduler jobs
```

## Set up

1. Install [uv](https://docs.astral.sh/uv/) and the [gcloud CLI](https://cloud.google.com/sdk/docs/install), then `uv sync`.
2. Create a Google Cloud project and a service account (`deploy.sh` makes one called `automations`). For running locally, download a key for it as `service-account.json`.
3. In Google Drive, make an Inbox folder, a Processed folder and a Clients folder. In Sheets, make a sheet with an `Invoices` tab and one with a `Clients` tab. Share them all with the service account's email as Editor. Service accounts have no Drive storage of their own, so a shared drive works best for the Clients folder.
4. For reminders, share the calendar with the service account ("See all event details") and create a Gmail [app password](https://myaccount.google.com/apppasswords) for `SMTP_PASSWORD`.
5. `cp .env.example .env` and fill it in. Folder and sheet ids are the long part of their URLs.

## Run

```
uv run pytest                                          # no keys needed
uv run python -m automations.invoice_inbox             # drop a PDF in Inbox first
uv run python -m automations.client_folder "Acme Ltd" jo@acme.com
uv run python -m automations.meeting_reminders
uv run uvicorn main:app --reload                       # the service, on localhost:8000
```

## Deploy

```
PROJECT=your-project-id ./deploy.sh
```

It deploys the service, creates the two scheduler jobs and prints the webhook URL for your CRM. Point the CRM's "new contact" webhook at `/run/client_folder` with the `X-Token` header, mapping its fields to `name` and `email`.

## Adding your own

Copy one file in `automations/`, change the steps, add it to `AUTOMATIONS` in `main.py`, then add a scheduler job or a webhook. Keep each step a plain function call. Use Claude for a step that needs judgment (reading, classifying, summarising) and plain code for everything else.

# Business automations

Replace typical n8n workflows with short Python scripts on Cloud Run. The workshop walkthrough is [WORKSHOP.md](WORKSHOP.md). Write-up and run of show for the first version: [Business automations workshop](https://docs.google.com/document/d/1ISDKj-E8gQt2X-PPXvds_KcveNmbQh35LJdjSzg5ZRY/edit).

Most n8n workflows are a trigger, then a few fixed steps: fetch something, maybe one AI call, write it somewhere. That is a Python function. Cloud Run hosts it, Cloud Scheduler or a webhook triggers it, and Claude handles the one step that needs judgment.

## What's here

| Automation | Trigger | What it does |
|---|---|---|
| [`invoice_inbox`](automations/invoice_inbox.py) | Cloud Scheduler, every 5 minutes | A PDF dropped in the Inbox folder in Drive becomes a row in the Invoices sheet (Claude reads it), then moves to Processed |
| [`client_folder`](automations/client_folder.py) | Webhook from your CRM or form | A new client gets a Drive folder with subfolders, and a row in the Clients sheet |
| [`meeting_reminders`](automations/meeting_reminders.py) | Cloud Scheduler, 8am daily | Every guest from outside the business gets a reminder email the day before |
| [`meeting_follow_up`](automations/meeting_follow_up.py) | Zoom webhook, when a transcript is ready | Claude summarises the call into the Meetings sheet and writes the client a follow-up email ("I'll send the proposal in the next 48 hours"), saved to Gmail drafts for you to check and send |

```
main.py          one service: POST /run/<name> (X-Token header) and POST /zoom (Zoom's signature)
automations/     one file per automation, each a run(payload) function
lib/             google.py (Drive, Sheets, Calendar), ai.py (one typed Claude call), mail.py (SMTP and Gmail drafts), zoom.py
src/             the step-by-step examples: three kinds of automation, see below
tests/           every automation and example against fakes, no keys needed
deploy.sh        Cloud Run plus the scheduler jobs
```

## Triggers: hello world, started three ways

[`triggers/`](triggers/) separates how an automation starts from what it does. [`hello_job.py`](triggers/hello_job.py) is one script that you run by hand (manual trigger) and that Cloud Scheduler runs every 5 minutes (scheduled trigger). [`hello_webhook.py`](triggers/hello_webhook.py) is a service that runs when its URL is called with the right token (webhook trigger). They need no Drive, Sheets or AI. `./deploy-examples.sh` deploys them and prints the commands to try each one.

The course outline is [COURSE.md](COURSE.md).

## Step by step: who decides the steps

[`src/`](src/) has one small example of each kind of automation. They differ in who decides the steps. 00 to 03 are jobs that run and stop. 04 is a service that waits for a webhook.

| Example | Who decides the steps | What it does |
|---|---|---|
| [`00-contract_filing.py`](src/00-contract_filing.py) | Code. No AI. | A signed contract named `Acme Ltd - contract.pdf` is filed in the client's folder and added to the Contracts tab of the CRM sheet |
| [`01-lead_research.py`](src/01-lead_research.py) | Code, with one AI call | Every day it searches Google for recruitment companies in South Wales and adds the ones it doesn't have yet to the Leads tab |
| [`02-call_notes.py`](src/02-call_notes.py) | Code, with one agent step | A call recording is transcribed (one model call), then an agent writes the call notes, looking up the client and earlier calls with two read-only tools. Both land in the CRM sheet |
| [`03-video_to_content.py`](src/03-video_to_content.py) | An agent, with tools written in code | A video becomes a transcript and the content drafts that suit it (Reel script, LinkedIn post, newsletter), each a row in the Content tab |
| [`04-webhook_to_sheet.py`](src/04-webhook_to_sheet.py) | Code. No AI. | The hello world of webhooks: a POST to its URL with the right token adds a row to the Webhook tab and says hello |

[`tools.py`](src/tools.py) holds every call to Drive, Sheets and Gemini. [`agent.py`](src/agent.py) is the agent loop, about 30 lines. The guardrails are in the tools, not the prompts: a handled file is never picked up twice, the same lead, note or draft is never saved twice, and the loop stops at a turn limit.

When to use which: if the steps are the same every run, let code decide them (00, 01, 02). If the path depends on what arrived, let an agent decide (03). Either way, write the tools as code.

There are no API keys. The examples run as Cloud Run jobs, and the job's service account is the login for Drive, Sheets and Gemini (through Vertex AI). They need:

- A CRM sheet with `Leads`, `Clients`, `Contracts`, `Call notes`, `Transcripts`, `Content` and `Webhook` tabs. 01 only needs the `Leads` tab.
- Three Drive folders: a contracts inbox, a recordings folder and a videos folder. Plus the Clients folder from the set up below, with a folder per client.
- All of them shared with the service account as Editor. Ordinary folders in your own Drive are fine: every output is a row in the sheet, because a service account can't create files in a personal Drive.
- The folder and sheet ids in `.env`, and a long random `WEBHOOK_TOKEN`.

```
PROJECT=your-project-id ./deploy-examples.sh                                    # one image, four jobs, the webhook service, a 9am schedule for 01
gcloud run jobs execute example-00-contract-filing --region europe-west2 --wait           # drop "Acme Ltd - contract.pdf" in the contracts inbox first
gcloud run jobs execute example-01-lead-research --region europe-west2 --wait          # empty the Leads tab first, then watch it fill
gcloud run jobs execute example-02-call-notes --region europe-west2 --wait      # drop a call recording in the recordings folder first
gcloud run jobs execute example-03-video-to-content --region europe-west2 --wait   # drop a video in the videos folder first
```

Each run handles whatever is new and prints JSON lines, so Cloud Scheduler can call the job on a timer. The deploy script puts 01 on one, every day at 9am, and prints the curl command for the webhook.

To run one on your own machine, use the service account key from step 2 below and install `ffmpeg`: `uv run python src/01-lead_research.py`.

## Set up

1. Install [uv](https://docs.astral.sh/uv/) and the [gcloud CLI](https://cloud.google.com/sdk/docs/install), then `uv sync`.
2. Create a Google Cloud project and a service account (`deploy.sh` makes one called `automations`). For running locally, download a key for it as `service-account.json`.
3. In Google Drive, make an Inbox folder, a Processed folder and a Clients folder. In Sheets, make a sheet with an `Invoices` tab and one with a `Clients` tab. Share them all with the service account's email as Editor. Service accounts have no Drive storage of their own, so a shared drive works best for the Clients folder.
4. For reminders, share the calendar with the service account ("See all event details") and create a Gmail [app password](https://myaccount.google.com/apppasswords) for `SMTP_PASSWORD`.
5. For meeting follow-up, add a `Meetings` tab to the Clients sheet. In the Zoom app marketplace, make a webhook-only app subscribed to "Recording transcript files have completed" (cloud recording with audio transcripts must be on), turn on "include download token", and copy its secret token to `ZOOM_WEBHOOK_SECRET`. The client's email comes from the calendar event that holds the Zoom link.
6. `cp .env.example .env` and fill it in. Folder and sheet ids are the long part of their URLs.

## Run

```
uv run pytest                                          # no keys needed
uv run python -m automations.invoice_inbox             # drop a PDF in Inbox first
uv run python -m automations.client_folder "Acme Ltd" jo@acme.com
uv run python -m automations.meeting_reminders
uv run python -m automations.meeting_follow_up transcript.vtt "Acme kick-off" jo@acme.com
uv run uvicorn main:app --reload                       # the service, on localhost:8000
```

## Deploy

```
PROJECT=your-project-id ./deploy.sh
```

It deploys the service, creates the two scheduler jobs and prints the webhook URLs for Zoom and your CRM. Point the CRM's "new contact" webhook at `/run/client_folder` with the `X-Token` header, mapping its fields to `name` and `email`.

## Adding your own

Copy one file in `automations/`, change the steps, add it to `AUTOMATIONS` in `main.py`, then add a scheduler job or a webhook. Keep each step a plain function call. Use Claude for a step that needs judgment (reading, classifying, summarising) and plain code for everything else.

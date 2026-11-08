# AI Engineer workshops

Code for the AI Engineer workshops. One folder per workshop. Each workshop's write-up (the plan, the talk track, the run of show) is a Google Doc in the AI Engineer Workshops folder in Drive, linked from the workshop's README.

| Workshop | What you build |
|---|---|
| [business-automations](business-automations/) | Python automations on Cloud Run that replace typical n8n workflows: a Drive invoice inbox that fills a Google Sheet, a Drive folder for every new client, and meeting reminders |

## Adding a workshop

1. Make a folder named after the workshop, in kebab-case.
2. Add a `README.md` with a link to the Google Doc, what members build, and how to set it up and run it.
3. Keep the code runnable on its own: its own `pyproject.toml`, `.env.example` and tests.
4. Add a row to the table above.

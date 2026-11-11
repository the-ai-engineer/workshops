# Business automations in code

The walkthrough for the workshop. Work through it top to bottom. Each section has what to say and, where there is a demo, what to run.

## Before you start

- [ ] `gcloud auth login` (the login expires about once a day)
- [ ] Set the project in the terminal you will demo from:

```bash
export PROJECT=personal-infrastructure-505708 REGION=europe-west2
```

- [ ] Run `./deploy-examples.sh` once so the jobs, the webhook and the schedule are live
- [ ] Open the CRM sheet in a browser tab and clear the `Leads` tab
- [ ] Have one call recording and one longer video ready to drop into Drive
- [ ] Open `src/` in the editor with `01-lead_research.py` on screen

## 1. What this workshop is about (3 min)

**Say**

- People keep asking me: what are the alternatives to n8n, and can't an agent just do this now?
- Today I'll show you how I build business automations for clients. It is simpler than you think.
- You will see four small automations, all running on Google Cloud, and how to choose between them.

## 2. Should you use n8n or code? (4 min)

Start with the honest answer, so nobody feels they are in the wrong room.

**Say**

- If you are not technical, n8n is the easier option. It is much easier to think about an automation when you can see it as a picture.
- A real benefit of n8n: the customer can open it, understand it, and even change it.
- Code is harder to read if you don't code, and harder to set up the first time.
- But once you have built one or two, they are simple. It is a Python script that runs on a schedule.
- If you want to build automations for businesses as a job, learn this. That is what today is for.

| | n8n | Code |
|---|---|---|
| Who can build it | Anyone | Someone technical, or someone with a coding agent |
| Who can change it later | The customer | You |
| Control, logs, alerts, tests | What the tool gives you | Whatever you need |
| Running it | Their cloud, or your own server to look after | A container that costs nothing when idle |
| Licence | Fine for internal use and consulting. Not for offering n8n itself to your customers | None |

## 3. What is a business automation? (4 min)

**Say**

- A task a person does again and again, done by a computer instead.
- Every automation is the same shape: something starts it, a few steps run, something comes out.

```
trigger  ->  steps  ->  output
```

- Why bother: it saves hours, it doesn't forget, and it runs while you sleep.
- Examples: new lead research, invoice intake, meeting follow-up, client onboarding.

## 4. The options today (4 min)

**Say**

- **Visual tools** like n8n, Zapier, Make. You draw the steps.
- **Agents** like Claude or Grok. You describe the job and the agent works out the steps.
- **Code.** You, or a coding agent, write the steps as a script.
- The new question is: now that Claude Code can write the script for me, do I still need the visual tool?
- My answer for professional work: no. Use a small Python script, in a container, on something like Cloud Run.
- Agents still have a place. We will come back to that in section 9.

## 5. Why code works well (5 min)

**Say**

- n8n makes you draw a graph. But most real automations are short. Boil the graph down and you get a list of steps and a few if/else statements.
- With code you control everything: logging, metrics, retries, alerts, tests, version history.
- That makes them more reliable. And they can still be very simple.

**Tell the real story**

- I work a lot with recruitment agencies. A common job there is lead research.
- For one client I run a researcher on Cloud Run. Every day it searches several places on the internet for new jobs.
- It is a messy task. You get rate limited. Sites change. You hit strange errors.
- This is where code pays off. When the job fails, which it sometimes does, I get an email telling me. I fix it before the client notices.
- Small things like that are what make it professional.

## 6. Where it runs, and the three triggers (5 min)

**Say**

- I deploy these to Cloud Run. AWS Lambda and others do the same thing.
- You hand it a container. It runs when triggered and costs nothing while idle. No server to look after.
- There are only three ways to start an automation:

| Trigger | What starts it | On Cloud Run | Example |
|---|---|---|---|
| Manual | You do | Run the job yourself | "Process this one file now" |
| Scheduled | The clock | Cloud Scheduler starts the job | "Every day at 9am" |
| Webhook | Another system | A service with a URL | "When a form is submitted" |

- A **job** starts, does the work and stops. A **service** waits for requests. Schedules and manual runs use jobs. Webhooks use a service.

## 7. Demo: lead research (12 min)

The simple one. It runs every day at 9am, searches the internet for companies, and adds them to a spreadsheet.

**Show the code:** [`src/01-lead_research.py`](src/01-lead_research.py). It is four steps.

```python
known = {row[1].strip().lower() for row in tools.read_rows(sheet, "Leads") if len(row) > 1}   # 1. what we have

found = tools.research(                                                                       # 2. one AI call
    f"Search Google for {QUERY}. List {PER_RUN} real companies that have their own website."
    f" Leave out these, which we already have: {', '.join(sorted(known)) or 'none'}.",
    Leads,
).leads

for lead in found:
    if lead.name.strip().lower() in known:                                                    # 3. skip repeats
        continue
    tools.add_row(sheet, "Leads", [date.today().isoformat(), lead.name, lead.website, lead.town, lead.specialism])  # 4. save
```

**Say**

- The code decides the order. It never changes.
- The AI does one step, the search, and has to answer in a fixed shape: name, website, town, specialism.
- The check for repeats is plain code. I don't trust the model to remember. I ask it, then I check.

**Manual trigger.** Put the empty `Leads` tab on screen, then:

```bash
gcloud run jobs execute example-01-lead-research --project $PROJECT --region $REGION --wait
```

Rows appear after about a minute. Run it again: ten new companies, no repeats.

**Scheduled trigger.** Show that the same job is on a timer:

```bash
gcloud scheduler jobs describe example-01-lead-research-daily --project $PROJECT --location $REGION
```

Point at `schedule: 0 9 * * *`. To fire the schedule now instead of waiting for 9am:

```bash
gcloud scheduler jobs run example-01-lead-research-daily --project $PROJECT --location $REGION
```

**Logs.** One line per run, so you can see what happened and alert on failures:

```bash
gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="example-01-lead-research"' --project $PROJECT --freshness 15m --format 'value(textPayload, jsonPayload)'
```

**Say**

- You could build this in n8n. But then you pay for their cloud or run your own server, for something that is a few lines of Python.

## 8. Demo: a webhook (6 min)

The hello world of automations. Another system calls a URL and the automation runs.

**Show the code:** [`src/04-webhook_to_sheet.py`](src/04-webhook_to_sheet.py).

```python
@app.post("/hook")
def hook(payload: dict = Body(default={}), x_token: str = Header(default="")) -> dict:
    if not hmac.compare_digest(x_token.encode(), os.environ["WEBHOOK_TOKEN"].encode()):
        raise HTTPException(401, "bad token")                    # 1. who is calling?

    name = str(payload.get("name", "world"))
    tools.add_row(os.environ["CLIENTS_SHEET_ID"], "Webhook", ...)  # 2. do the work
    return {"message": f"Hello, {name}!"}                         # 3. reply
```

**Run it.** Put the `Webhook` tab on screen, then:

```bash
export URL=$(gcloud run services describe example-04-webhook-to-sheet --project $PROJECT --region $REGION --format 'value(status.url)')
```

```bash
export WEBHOOK_TOKEN=$(grep '^WEBHOOK_TOKEN=' .env | cut -d= -f2)
```

```bash
curl -X POST $URL/hook -H "Authorization: Bearer $(gcloud auth print-identity-token)" -H "X-Token: $WEBHOOK_TOKEN" -H "Content-Type: application/json" -d '{"name": "Owain"}'
```

A row appears and the reply is `{"message":"Hello, Owain!"}`. Then show what a caller with the wrong token gets (401, `bad token`):

```bash
curl -X POST $URL/hook -H "Authorization: Bearer $(gcloud auth print-identity-token)" -H "X-Token: wrong" -H "Content-Type: application/json" -d '{"name": "Stranger"}'
```

Note for you: this project's organisation blocks public URLs, so the service is not public yet and Google itself turns away anyone who is not signed in (403). That is why the curl carries the `Authorization` header. If you make the service public, drop that header and the demo is the same.

**Say**

- A webhook URL is normally public, so the first step is always to check who is calling. Here it is a secret token. Stripe and Zoom sign their requests instead.
- Swap the middle step for anything: create a client folder, send an email, start the lead research.
- This is the URL you paste into a form tool, a CRM or Stripe.

## 9. Where does AI fit? Who decides the steps (5 min)

This answers "can't an agent just do it?".

**Say**

- The useful question is not "AI or no AI". It is: who decides the steps, the code or the model?

| Example | Who decides the steps | Use it when |
|---|---|---|
| `00-contract_filing.py` | Code. No AI. | Rules are enough |
| `01-lead_research.py` | Code, with one AI call | One step needs reading, writing or searching |
| `02-call_notes.py` | Code, with one agent step | One step is open-ended |
| `03-video_to_content.py` | An agent, using tools written in code | The path depends on what arrived |

- An agent is a loop: the model picks a tool, the code runs it, repeat. Show [`src/agent.py`](src/agent.py). It is about 30 lines.
- If the steps are the same every run, let code decide. It is cheaper, faster and never skips a step.
- If the path changes with the input, let an agent decide. But write the tools as code, and put the safety rules in the tools, not the prompt.

## 10. Demo: an agent as one step (8 min)

A call recording becomes notes in the CRM.

**Show the code:** [`src/02-call_notes.py`](src/02-call_notes.py). Five steps, and only step 3 is an agent.

**Run it.** Drop a call recording into the `Recordings` folder, then:

```bash
gcloud run jobs execute example-02-call-notes --project $PROJECT --region $REGION --wait
```

Show the `Transcripts` and `Call notes` tabs. Then show the agent's path in the logs:

```bash
gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="example-02-call-notes"' --project $PROJECT --freshness 15m --order asc --format 'value(textPayload)'
```

**Say**

- The agent chose to look up the client list, then the earlier notes. I did not tell it the order.
- It is fenced in: two tools that only read, a turn limit, and if it fails the transcript is still saved.

## 11. Demo: the agent decides everything (8 min)

A video becomes content drafts. The agent picks which ones.

**Show the code:** [`src/03-video_to_content.py`](src/03-video_to_content.py). Point at the three tools and at `save_draft`.

**Run it.** Drop a video into the `Videos` folder, then:

```bash
gcloud run jobs execute example-03-video-to-content --project $PROJECT --region $REGION --wait
```

Show the `Content` tab and the report line in the logs.

**Say**

- A short clip gets a Reel script only. A long talk gets a LinkedIn post and a newsletter too. Same code, different path.
- The safety is in the tools. `save_draft` refuses a format that is not on the list and never saves the same draft twice. The prompt cannot talk its way past that.
- Look at the token counts in the logs. The agent run costs several times what the single AI call did. That is the price of letting the model decide.

## 12. How to choose (4 min)

**Say**

- Not technical, and the customer wants to edit it: n8n.
- A one-off, or you are still working out the steps: do it with an agent by hand.
- Runs often, same steps every time: a script. This is most business automations.
- Runs often, and one step needs judgement: a script with one agent step.
- The path really does change with the input: an agent with tools you wrote.
- Three questions settle most cases: How often does it run? What does a mistake cost? Is anyone watching?

## 13. Running these for real (4 min)

**Say**

- **Logs.** Print one line per run. Cloud Run keeps them and you can search them.
- **Alerts.** Have a failed run send you an email. This is the single most useful thing you can add.
- **Don't do things twice.** Every example skips work it has already done, so a retry is safe.
- **Secrets.** Keep tokens in Secret Manager, not in the code.
- **Cost.** The container is free while idle. You pay for the seconds it runs and for the AI calls. Searches with Google are billed per request on top of tokens, so check the current price before you run one every minute.
- **Check the AI's work.** The leads are whatever the model found. For a client, add a step that checks each website exists.

## 14. Wrap up and questions

**Say**

- An automation is a trigger, a few steps and an output.
- A Python script on Cloud Run covers most of them.
- Use AI for the steps that need it. Use an agent only where the path really changes.
- The repo is yours. Copy one file in `src/`, change the steps, deploy.

**Ask the room:** what is one task in your business you would automate first, and which of the four would it be?

# Run every demo

Every demo in the course, in order, with the commands to copy. Most demos run twice: once on your laptop and once on Google Cloud. The automation is the same file both times.

Run every command from the `ai-automation-course` folder.

## Set up, once

### 1. The settings file

```
cp .env.example .env
```

Open `.env` and fill it in:

| Setting | What to put |
|---|---|
| `PROJECT` | Your Google Cloud project id |
| `SHEET_ID` | The long part of your Google Sheet's address |
| `WEBHOOK_TOKEN`, `WEBHOOK_SECRET` | Two long random values. Run `openssl rand -hex 24` twice |
| `SLACK_WEBHOOK_URL` | A Slack incoming webhook address |
| `RESEND_API_KEY`, `EMAIL_FROM` | A Resend key, and an address on a domain you verified there |
| `TEST_LEAD_EMAIL` | Your own address. The test proposal is sent here |

Leave `SHADOW=true` for now.

### 2. The sheet

Make a Google Sheet with two tabs. Put these headings in the first row of each, so the sheet is easy to read on screen:

- `Prospects`: Date, Company, Signal, Published, Source, Status
- `Leads`: Time, Lead id, Name, Email, Company, Message, Proposal, Status

### 3. Point this terminal at your project

Do this in every new terminal. It sets the project for that terminal only, so a different default project can't catch you out.

```
export CLOUDSDK_CORE_PROJECT=$(grep '^PROJECT=' .env | cut -d= -f2)
gcloud auth login
```

### 4. Deploy

Run this before Demo 4, so there is something to look at in the console. Demo 5a shows the same command, and Demo 8 walks through what it does.

```
./deploy.sh
```

It takes a few minutes the first time. At the end it prints the email of the `automations` service account. Share your sheet with that email as Editor.

Then save the two webhook addresses and the token for later:

```
export HELLO_URL=$(gcloud run services describe hello-webhook --region europe-west2 --format 'value(status.url)')
export LEAD_URL=$(gcloud run services describe speed-to-lead --region europe-west2 --format 'value(status.url)')
export WEBHOOK_TOKEN=$(grep '^WEBHOOK_TOKEN=' .env | cut -d= -f2)
```

### 5. Let your laptop sign in as the automations account

The laptop runs of daily research and speed to lead read the real sheet and call the real model. Sign in once as the same account Cloud Run uses. There is no key file.

```
SA=automations@$CLOUDSDK_CORE_PROJECT.iam.gserviceaccount.com
gcloud iam service-accounts add-iam-policy-binding $SA --member "user:$(gcloud config get-value account)" --role roles/iam.serviceAccountTokenCreator
gcloud auth application-default login --impersonate-service-account $SA
```

The first command can take a minute to apply. To go back to your own login later, run `gcloud auth application-default login`.

### 6. Set up the alert

Do this at least five minutes before Demo 12. A new rule takes a few minutes to start watching.

```
ALERT_EMAIL=you@example.com ./alerts.sh
```

If the project runs other things too, watch only these automations:

```
NAMES='^(hello-|daily-research|speed-to-lead)' ALERT_EMAIL=you@example.com ./alerts.sh
```

### If your Google organisation blocks public URLs

Some organisations don't allow a public Cloud Run service. The deploy still works, with a warning about the IAM policy, and every call to a webhook returns 403 before your code runs. Sign in to Google on each call as well:

- With `curl`, add `-H "Authorization: Bearer $(gcloud auth print-identity-token)"`.
- With `tools/send_lead.py`, add `--private`.

## Demo 4: the Google Cloud console

Print the pages to open, in the order to show them:

```
for page in run cloudscheduler logs/query security/secret-manager vertex-ai iam-admin/serviceaccounts billing; do echo "https://console.cloud.google.com/$page?project=$CLOUDSDK_CORE_PROJECT"; done
```

## Demo 5a: manual

On your laptop:

```
uv run python automations/01_manual.py
```

On Google Cloud:

```
gcloud run jobs execute hello-manual --region europe-west2 --wait
```

Read what it logged. Logs take up to half a minute to arrive.

```
gcloud logging read 'jsonPayload.automation="01_manual"' --freshness 15m --format 'value(timestamp, jsonPayload.result.message)'
```

## Demo 5b: scheduled

On your laptop:

```
uv run python automations/02_scheduled.py
```

On Google Cloud. Look at the schedule, turn it on, and fire it now:

```
gcloud scheduler jobs describe hello-every-5-minutes --location europe-west2
gcloud scheduler jobs resume hello-every-5-minutes --location europe-west2
gcloud scheduler jobs run hello-every-5-minutes --location europe-west2
```

Read the log, then pause the schedule:

```
gcloud logging read 'jsonPayload.automation="02_scheduled"' --freshness 15m --format 'value(timestamp, jsonPayload.result.message)'
gcloud scheduler jobs pause hello-every-5-minutes --location europe-west2
```

## Demo 5c: webhook

On your laptop. Start it in one terminal:

```
uv run python automations/03_webhook.py
```

Call it from a second terminal:

```
curl -X POST http://localhost:8080/hook -H "X-Token: $WEBHOOK_TOKEN" -H "Content-Type: application/json" -d '{"name": "Owain"}'
```

Stop the first terminal with Ctrl+C.

On Google Cloud, with the right token and then the wrong one:

```
curl -X POST $HELLO_URL/hook -H "X-Token: $WEBHOOK_TOKEN" -H "Content-Type: application/json" -d '{"name": "Owain"}'
curl -X POST $HELLO_URL/hook -H "X-Token: wrong" -H "Content-Type: application/json" -d '{"name": "Owain"}'
```

The first replies `{"message":"Hello, Owain!"}`. The second is a 401, `bad token`.

## Demo 6: build speed to lead live

Commit your work first, so nothing can be lost. Then move the finished files aside:

```
mkdir -p ~/course-aside
mv automations/05_speed_to_lead.py tests/test_speed_to_lead.py ~/course-aside/
```

Open Claude Code in this folder and give it the prompt from Lesson 6. When you're done, put the finished files back:

```
mv ~/course-aside/05_speed_to_lead.py automations/
mv ~/course-aside/test_speed_to_lead.py tests/
```

## Demo 7: the tests, then shadow mode

```
uv run pytest
```

On your laptop, with `SHADOW=true` in `.env`. Start it in one terminal:

```
uv run python automations/05_speed_to_lead.py
```

Send a signed lead from a second terminal:

```
uv run python tools/send_lead.py http://localhost:8080
```

The reply is `"status": "proposal ready (shadow mode)"`. In the first terminal, the `"would": "send email"` line has the full proposal. Nothing was sent. The lead is saved to the `Leads` tab.

Send a bad form. It gets a 400 and nothing is saved:

```
uv run python tools/send_lead.py http://localhost:8080 --bad
```

Stop the first terminal with Ctrl+C.

## Demo 8: the live deploy

Set `SHADOW=false` in `.env`, then deploy:

```
./deploy.sh
```

Show the secrets it made, and that the service gets them as secrets:

```
gcloud secrets list
gcloud run services describe speed-to-lead --region europe-west2 --format 'yaml(spec.template.spec.containers[0].env)'
```

Send a real lead. The same email and message twice is a repeat, and a repeat is skipped. The lead from Demo 7 is already in the sheet, so send a new message:

```
uv run python tools/send_lead.py $LEAD_URL --message "We spend two days a month matching invoices to purchase orders by hand. Can you automate it?"
```

The Slack message arrives, the email arrives at `TEST_LEAD_EMAIL`, and the row lands in the sheet.

## The enquiry form: the same demo from a web page

`tools/form.py` is a small website with an enquiry form. Its backend signs each form and calls the webhook, the way a real site would. The email field is filled in with `TEST_LEAD_EMAIL`, so the proposal comes to you.

On your laptop. Start the webhook in one terminal:

```
uv run python automations/05_speed_to_lead.py
```

Start the form in a second terminal, then open http://127.0.0.1:8770:

```
uv run python tools/form.py
```

On Google Cloud, point the form at the live webhook:

```
uv run python tools/form.py $LEAD_URL
```

Fill it in and send it. The page shows the webhook's reply and how long it took. Change the message each time: the same email and message twice is a repeat, and a repeat is skipped.

## Demo 9: three calls to the live webhook

```
uv run python tools/send_lead.py $LEAD_URL
uv run python tools/send_lead.py $LEAD_URL --tamper
curl -X POST $LEAD_URL/hook -H "Content-Type: application/json" -d '{"name": "Eve"}'
```

The first is accepted. It replies `duplicate`, because this lead is already in the sheet. The second and third are 401. Then show the two rejections in the logs:

```
gcloud logging read 'jsonPayload.status="rejected"' --freshness 15m --limit 5 --format 'value(timestamp, jsonPayload.automation, jsonPayload.reason)'
```

## Demo 10: daily research

Clear the rows under the headings in the `Prospects` tab.

On your laptop. Slack is only told when `SHADOW=false`:

```
uv run python automations/04_daily_research.py
```

On Google Cloud. Run it twice. The second run adds nothing twice:

```
gcloud run jobs execute daily-research --region europe-west2 --wait
gcloud run jobs execute daily-research --region europe-west2 --wait
```

Show the schedule that starts it at 7am on weekdays:

```
gcloud scheduler jobs describe daily-research-weekdays --location europe-west2
```

## Demo 11: receipts and video to content (optional)

These two live in the workshop folder and have their own deploy script. See [`../business-automations/README.md`](../business-automations/README.md) for the sheet tabs and Drive folders they need.

```
cd ../business-automations
./deploy-examples.sh
gcloud run jobs execute example-05-receipts --region europe-west2 --wait
gcloud run jobs execute example-06-video-to-content --region europe-west2 --wait
cd ../ai-automation-course
```

Drop a receipt or a video into its folder before each run. To read the tools the agent called, in order:

```
gcloud logging read 'resource.labels.job_name="example-06-video-to-content" AND textPayload:("tool:" OR "agent:")' --freshness 15m --order asc --format 'value(textPayload)'
```

## Demo 12: three failures, on purpose

The alert from step 6 must be at least five minutes old.

Break 1: the model goes down. Send a lead. The team still hears, and the lead is saved as `needs a person`. Then put the model back.

```
gcloud run services update speed-to-lead --region europe-west2 --update-env-vars GEMINI_MODEL=does-not-exist
uv run python tools/send_lead.py $LEAD_URL --message "Our stock counts never match the system. Can you help?"
gcloud run services update speed-to-lead --region europe-west2 --update-env-vars GEMINI_MODEL=$(grep '^GEMINI_MODEL=' .env | cut -d= -f2)
```

Break 2: a job fails. The run fails, the ERROR line is in the logs, and the alert email arrives. Then put the sheet back and run it again.

```
gcloud run jobs update daily-research --region europe-west2 --update-env-vars SHEET_ID=wrong
gcloud run jobs execute daily-research --region europe-west2 --wait
gcloud logging read 'severity>=ERROR AND jsonPayload.automation="04_daily_research"' --freshness 15m --limit 1 --format 'value(timestamp, jsonPayload.error)'
gcloud run jobs update daily-research --region europe-west2 --update-env-vars SHEET_ID=$(grep '^SHEET_ID=' .env | cut -d= -f2)
gcloud run jobs execute daily-research --region europe-west2 --wait
```

Break 3: the same lead twice. The second reply is `duplicate`, and one email goes out.

```
uv run python tools/send_lead.py $LEAD_URL --message "We re-key every order from email into our system. Can you help?"
uv run python tools/send_lead.py $LEAD_URL --message "We re-key every order from email into our system. Can you help?"
```

## When you're done

Daily research keeps running every weekday at 7am until you pause it:

```
gcloud scheduler jobs pause daily-research-weekdays --location europe-west2
gcloud scheduler jobs list --location europe-west2
```

## If something goes wrong

| What you see | What to do |
|---|---|
| `NOT_FOUND`, or resources from a different project | This terminal isn't pointed at your project. Run the `export CLOUDSDK_CORE_PROJECT` line from step 3 |
| `Reauthentication` from a `gcloud` command | Run `gcloud auth login` again |
| `Reauthentication is needed` from a laptop run | Run the last command in step 5 again |
| A webhook returns 403 before your code runs | Your organisation blocks public URLs. See the section above |
| A laptop run fails with a 403 or 404 from Sheets | The sheet isn't shared with the `automations` account, or `SHEET_ID` is wrong |
| The logs command prints nothing | Logs take up to half a minute. Run it again |
| A lead comes back `duplicate` | That email and message are already in the `Leads` tab. Send a new `--message` |
| The model call fails with `not found` | The model isn't offered in `VERTEX_LOCATION`. Pick a region that has it |
| No alert email | The rule is under five minutes old, or it sent an email in the last five minutes. It sends at most one every five minutes |

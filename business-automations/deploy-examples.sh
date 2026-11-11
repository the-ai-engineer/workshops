#!/usr/bin/env bash
# Deploy the step-by-step examples in src/ to Cloud Run: a job per example, a
# service for the webhook, and a schedule for the lead research.
# Needs: gcloud signed in, PROJECT set, and the ids and WEBHOOK_TOKEN in .env.
# There are no API keys. Everything runs as the automations service account, and
# that account is the login for Drive, Sheets and Gemini (through Vertex AI).
set -euo pipefail

PROJECT="${PROJECT:?set PROJECT to your Google Cloud project id}"
REGION="${REGION:-europe-west2}"
ACCOUNT="automations@${PROJECT}.iam.gserviceaccount.com"
BUILDER="automations-build@${PROJECT}.iam.gserviceaccount.com"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/automations/examples"

gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  cloudscheduler.googleapis.com aiplatform.googleapis.com drive.googleapis.com sheets.googleapis.com \
  --project "$PROJECT"

# The identity everything runs as. Share your Drive folders and the CRM sheet with this email.
gcloud iam service-accounts describe "$ACCOUNT" --project "$PROJECT" >/dev/null 2>&1 ||
  gcloud iam service-accounts create automations --display-name "Business automations" --project "$PROJECT"
# Lets it call Gemini on Vertex AI.
gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:$ACCOUNT" \
  --role roles/aiplatform.user --condition None >/dev/null

# The identity that builds the image. Newer projects give Cloud Build's default account
# no permissions, so the script makes its own and the build works either way.
gcloud iam service-accounts describe "$BUILDER" --project "$PROJECT" >/dev/null 2>&1 ||
  gcloud iam service-accounts create automations-build --display-name "Builds the automations image" --project "$PROJECT"
gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:$BUILDER" \
  --role roles/cloudbuild.builds.builder --condition None >/dev/null

# Build the image once. Every job and the webhook use it, each with a different command.
gcloud artifacts repositories describe automations --location "$REGION" --project "$PROJECT" >/dev/null 2>&1 ||
  gcloud artifacts repositories create automations --repository-format docker --location "$REGION" --project "$PROJECT"
for attempt in 1 2 3 4; do  # a brand-new build account takes about a minute to get its permissions
  gcloud builds submit --tag "$IMAGE" --project "$PROJECT" \
    --service-account "projects/${PROJECT}/serviceAccounts/${BUILDER}" \
    --default-buckets-behavior regional-user-owned-bucket && break
  [ "$attempt" -lt 4 ] || exit 1
  echo "Build failed, trying again in 30 seconds..."
  sleep 30
done

KEYS="CLIENTS_FOLDER_ID|CLIENTS_SHEET_ID|CONTRACTS_INBOX_ID|RECORDINGS_FOLDER_ID|VIDEOS_FOLDER_ID|GEMINI_MODEL|LEADS_QUERY|LEADS_PER_RUN"
# "^|^" makes | the separator, so a value can contain commas and spaces.
VARS="^|^GOOGLE_CLOUD_PROJECT=${PROJECT}|$(grep -E "^(${KEYS})=." .env | paste -sd"|" -)"

job() {  # job name, script, memory
  # No retries: the next run picks up whatever is left.
  gcloud run jobs deploy "$1" --project "$PROJECT" --region "$REGION" --image "$IMAGE" \
    --service-account "$ACCOUNT" --set-env-vars "$VARS" \
    --command uv --args "run,--no-dev,python,$2" \
    --memory "${3:-512Mi}" --task-timeout 30m --max-retries 0
}

service() {  # service name, script. A public URL; the code checks the X-Token header.
  # The token goes in as an environment variable to keep the course short. For a client, use Secret Manager.
  gcloud run deploy "$1" --project "$PROJECT" --region "$REGION" --image "$IMAGE" \
    --service-account "$ACCOUNT" --set-env-vars "$VARS|$(grep '^WEBHOOK_TOKEN=.' .env)" \
    --command uv --args "run,--no-dev,python,$2" --allow-unauthenticated
}

schedule() {  # schedule name, cron, job to start
  gcloud run jobs add-iam-policy-binding "$3" --project "$PROJECT" --region "$REGION" \
    --member "serviceAccount:$ACCOUNT" --role roles/run.invoker >/dev/null
  gcloud scheduler jobs delete "$1" --project "$PROJECT" --location "$REGION" --quiet >/dev/null 2>&1 || true
  gcloud scheduler jobs create http "$1" --project "$PROJECT" --location "$REGION" \
    --schedule "$2" --time-zone "Europe/London" --http-method POST \
    --uri "https://run.googleapis.com/v2/projects/${PROJECT}/locations/${REGION}/jobs/$3:run" \
    --oauth-service-account-email "$ACCOUNT"
}

url() { gcloud run services describe "$1" --project "$PROJECT" --region "$REGION" --format 'value(status.url)'; }

# Module 1, triggers: hello world started three ways.
job example-hello triggers/hello_job.py                       # 1. manual: you run the job
schedule example-hello-every-5-minutes "*/5 * * * *" example-hello   # 2. scheduled: the clock runs the same job
service example-hello-webhook triggers/hello_webhook.py        # 3. webhook: a request runs it

# Module 2, workflows. The two that download recordings get 2Gi, because the file is held in memory.
job example-00-contract-filing src/00-contract_filing.py
job example-01-lead-research src/01-lead_research.py
job example-02-call-notes src/02-call_notes.py 2Gi
job example-03-video-to-content src/03-video_to_content.py 2Gi
service example-04-webhook-to-sheet src/04-webhook_to_sheet.py
schedule example-01-lead-research-daily "0 9 * * *" example-01-lead-research  # the lead research, every day at 9am

G="--project $PROJECT --region $REGION"
echo
echo "Share your Drive folders and the CRM sheet with: $ACCOUNT"
echo
echo "1. Manual:     gcloud run jobs execute example-hello $G --wait"
echo "2. Scheduled:  runs every 5 minutes. To stop it: gcloud scheduler jobs pause example-hello-every-5-minutes --project $PROJECT --location $REGION"
echo "3. Webhook:    curl -X POST $(url example-hello-webhook)/hook -H \"X-Token: \$WEBHOOK_TOKEN\" -H 'Content-Type: application/json' -d '{\"name\": \"Owain\"}'"
echo "   Logs:       gcloud logging read 'resource.labels.job_name=\"example-hello\" AND textPayload:Hello' --project $PROJECT --freshness 15m --format 'value(timestamp, textPayload)'"
echo
echo "Lead research: gcloud run jobs execute example-01-lead-research $G --wait"
echo "CRM webhook:   curl -X POST $(url example-04-webhook-to-sheet)/hook -H \"X-Token: \$WEBHOOK_TOKEN\" -H 'Content-Type: application/json' -d '{\"name\": \"Owain\"}'"

#!/usr/bin/env bash
# Deploy every example in examples/ to Cloud Run: a job or a service for each,
# and the schedules that start the jobs.
# Needs: gcloud signed in, PROJECT set, and a .env file (see .env.example).
# There are no API keys. Everything runs as the automations service account, and
# that account is the login for Sheets, Drive and Gemini (through Vertex AI).
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

KEYS="SHEET_ID|RECEIPTS_FOLDER_ID|VIDEOS_FOLDER_ID|SLACK_WEBHOOK_URL|GEMINI_MODEL"
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

job example-hello examples/01-hello_job.py                            # manual: you run the job
schedule example-hello-every-5-minutes "*/5 * * * *" example-hello   # scheduled: the clock runs the same job
service example-hello-webhook examples/02-hello_webhook.py           # webhook: a request runs it
job example-03-job-leads examples/03-job_leads.py
schedule example-03-job-leads-daily "0 9 * * *" example-03-job-leads  # job leads, every day at 9am
service example-04-speed-to-lead examples/04-speed_to_lead.py
job example-05-receipts examples/05-receipts.py
schedule example-05-receipts-check "*/15 * * * *" example-05-receipts   # look for new receipts every 15 minutes
job example-06-video-to-content examples/06-video_to_content.py 2Gi      # the video is held in memory
schedule example-06-video-to-content-check "*/15 * * * *" example-06-video-to-content

G="--project $PROJECT --region $REGION"
echo
echo "Share your sheet and your Drive folders with: $ACCOUNT"
echo
echo "1. Manual:     gcloud run jobs execute example-hello $G --wait"
echo "2. Scheduled:  runs every 5 minutes. To stop it: gcloud scheduler jobs pause example-hello-every-5-minutes --project $PROJECT --location $REGION"
echo "3. Webhook:    curl -X POST $(url example-hello-webhook)/hook -H \"X-Token: \$WEBHOOK_TOKEN\" -H 'Content-Type: application/json' -d '{\"name\": \"Owain\"}'"
echo "   Logs:       gcloud logging read 'resource.labels.job_name=\"example-hello\" AND textPayload:Hello' --project $PROJECT --freshness 15m --format 'value(timestamp, textPayload)'"
echo
echo "Job leads:     gcloud run jobs execute example-03-job-leads $G --wait"
echo "Speed to lead: curl -X POST $(url example-04-speed-to-lead)/hook -H \"X-Token: \$WEBHOOK_TOKEN\" -H 'Content-Type: application/json' -d '{\"name\": \"Sam Price\", \"email\": \"sam@example.com\", \"message\": \"We need two site managers.\"}'"
echo "Receipts:      gcloud run jobs execute example-05-receipts $G --wait"
echo "Video:         gcloud run jobs execute example-06-video-to-content $G --wait"

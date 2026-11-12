#!/usr/bin/env bash
# Deploy every automation to Cloud Run: a job or a service for each, the
# schedules that start the jobs, and the secrets they need.
#
#   ./deploy.sh
#
# Needs: gcloud signed in, and a .env file (copy .env.example).
# There are no keys for Google. Everything runs as the automations service
# account, and that account is the login for Sheets and Gemini on Vertex AI.
set -euo pipefail
cd "$(dirname "$0")"
setting() { grep -s "^$1=" .env | cut -d= -f2- || true; }

PROJECT="${PROJECT:-$(setting PROJECT)}"
: "${PROJECT:?set PROJECT in .env to your Google Cloud project id}"
REGION="${REGION:-$(setting REGION)}"
REGION="${REGION:-europe-west2}"
ACCOUNT="automations@${PROJECT}.iam.gserviceaccount.com"
BUILDER="automations-build@${PROJECT}.iam.gserviceaccount.com"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/automations/course"
G="--project $PROJECT --region $REGION"

# 1. Turn on the services we use.
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  cloudscheduler.googleapis.com aiplatform.googleapis.com sheets.googleapis.com \
  secretmanager.googleapis.com --project "$PROJECT"

# 2. The identity every automation runs as. Share your sheet with this email.
gcloud iam service-accounts describe "$ACCOUNT" --project "$PROJECT" >/dev/null 2>&1 ||
  gcloud iam service-accounts create automations --display-name "Automations" --project "$PROJECT"
# It may call Gemini on Vertex AI. That's the only project-wide permission it gets.
gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:$ACCOUNT" \
  --role roles/aiplatform.user --condition None >/dev/null

# 3. Secrets: copy each one from .env into Secret Manager, and let the service account read it.
for name in WEBHOOK_TOKEN WEBHOOK_SECRET SLACK_WEBHOOK_URL RESEND_API_KEY; do
  value="$(setting "$name")"
  [ -n "$value" ] || { echo "Skipping $name: it isn't set in .env"; continue; }
  secret="$(echo "$name" | tr 'A-Z_' 'a-z-')"
  gcloud secrets describe "$secret" --project "$PROJECT" >/dev/null 2>&1 ||
    gcloud secrets create "$secret" --replication-policy automatic --project "$PROJECT"
  printf '%s' "$value" | gcloud secrets versions add "$secret" --data-file - --project "$PROJECT" >/dev/null
  gcloud secrets add-iam-policy-binding "$secret" --member "serviceAccount:$ACCOUNT" \
    --role roles/secretmanager.secretAccessor --project "$PROJECT" >/dev/null
done
secret() { echo "$1=$(echo "$1" | tr 'A-Z_' 'a-z-'):latest"; }

# 4. Build one image. Every job and service runs it with a different command.
# A second account does the build. Newer projects give Cloud Build's default account
# no permissions, so the script makes its own and the build works either way.
gcloud iam service-accounts describe "$BUILDER" --project "$PROJECT" >/dev/null 2>&1 ||
  gcloud iam service-accounts create automations-build --display-name "Builds the automations image" --project "$PROJECT"
gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:$BUILDER" \
  --role roles/cloudbuild.builds.builder --condition None >/dev/null
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

# Plain settings. "^|^" makes | the separator, so a value can contain commas.
VARS="^|^GOOGLE_CLOUD_PROJECT=${PROJECT}|$(grep -E '^(SHEET_ID|SHADOW|GEMINI_MODEL|VERTEX_LOCATION|EMAIL_FROM)=.' .env | paste -sd'|' -)"

job() {  # name, file, secrets
  # No automatic retries: every job is safe to run again, and the next run picks up what's left.
  gcloud run jobs deploy "$1" $G --image "$IMAGE" --service-account "$ACCOUNT" \
    --set-env-vars "$VARS" ${3:+--set-secrets "$3"} \
    --command uv --args "run,--no-dev,python,$2" --task-timeout 15m --max-retries 0
}

service() {  # name, file, secrets
  # Public, because a website form or another company calls it. The code checks every request.
  # For a caller that's yours, use --no-allow-unauthenticated: then Google checks who is calling.
  gcloud run deploy "$1" $G --image "$IMAGE" --service-account "$ACCOUNT" \
    --set-env-vars "$VARS" ${3:+--set-secrets "$3"} \
    --command uv --args "run,--no-dev,python,$2" --allow-unauthenticated
}

schedule() {  # name, cron, job
  gcloud run jobs add-iam-policy-binding "$3" $G --member "serviceAccount:$ACCOUNT" --role roles/run.invoker >/dev/null
  gcloud scheduler jobs delete "$1" --project "$PROJECT" --location "$REGION" --quiet >/dev/null 2>&1 || true
  gcloud scheduler jobs create http "$1" --project "$PROJECT" --location "$REGION" \
    --schedule "$2" --time-zone "Europe/London" --http-method POST \
    --uri "https://run.googleapis.com/v2/projects/${PROJECT}/locations/${REGION}/jobs/$3:run" \
    --oauth-service-account-email "$ACCOUNT"
}

# 5. The automations. Adding one is one more line.
job hello-manual automations/01_manual.py
job hello-scheduled automations/02_scheduled.py
schedule hello-every-5-minutes "*/5 * * * *" hello-scheduled
gcloud scheduler jobs pause hello-every-5-minutes --project "$PROJECT" --location "$REGION"  # turn it on when you want it
service hello-webhook automations/03_webhook.py "$(secret WEBHOOK_TOKEN)"
job daily-research automations/04_daily_research.py "$(secret SLACK_WEBHOOK_URL)"
schedule daily-research-weekdays "0 7 * * 1-5" daily-research
service speed-to-lead automations/05_speed_to_lead.py \
  "$(secret WEBHOOK_SECRET),$(secret SLACK_WEBHOOK_URL),$(secret RESEND_API_KEY)"

url() { gcloud run services describe "$1" $G --format 'value(status.url)'; }
echo
echo "Share your sheet with: $ACCOUNT"
echo
echo "01 manual:        gcloud run jobs execute hello-manual $G --wait"
echo "02 scheduled:     gcloud scheduler jobs resume hello-every-5-minutes --project $PROJECT --location $REGION"
echo "03 webhook:       curl -X POST $(url hello-webhook)/hook -H \"X-Token: \$WEBHOOK_TOKEN\" -d '{\"name\": \"Owain\"}'"
echo "04 research:      gcloud run jobs execute daily-research $G --wait"
echo "05 speed to lead: uv run python tools/send_lead.py $(url speed-to-lead)"
echo
echo "Logs:             gcloud logging read 'jsonPayload.automation:*' --project $PROJECT --freshness 1h --limit 20"

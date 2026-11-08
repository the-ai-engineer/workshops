#!/usr/bin/env bash
# Deploy the service to Cloud Run and schedule the timed automations.
# Needs: gcloud signed in, PROJECT and REGION set, and a filled-in .env.
set -euo pipefail

PROJECT="${PROJECT:?set PROJECT to your Google Cloud project id}"
REGION="${REGION:-europe-west2}"
SERVICE=business-automations
ACCOUNT="automations@${PROJECT}.iam.gserviceaccount.com"

env_value() { grep "^$1=" .env | cut -d= -f2-; }
AUTOMATION_TOKEN=$(env_value AUTOMATION_TOKEN)
TIMEZONE=$(env_value TIMEZONE)

gcloud config set project "$PROJECT"
gcloud services enable run.googleapis.com cloudscheduler.googleapis.com cloudbuild.googleapis.com \
  drive.googleapis.com sheets.googleapis.com calendar-json.googleapis.com

# The identity the automations run as. Share your folders, sheets and calendar with this email.
gcloud iam service-accounts describe "$ACCOUNT" >/dev/null 2>&1 ||
  gcloud iam service-accounts create automations --display-name "Business automations"

# The keys go in as environment variables here to keep the workshop short.
# For a client, put ANTHROPIC_API_KEY, AUTOMATION_TOKEN and SMTP_PASSWORD in Secret Manager instead.
# "^|^" makes | the separator, so values can contain commas, spaces and @.
VARS="^|^$(grep -v '^#' .env | grep '=' | grep -v '^GOOGLE_APPLICATION_CREDENTIALS=' | paste -sd"|" -)"

gcloud run deploy "$SERVICE" --source . --region "$REGION" \
  --service-account "$ACCOUNT" --allow-unauthenticated \
  --set-env-vars "$VARS" --timeout 300 --no-cpu-throttling  # CPU stays on so the Zoom follow-up can finish after the reply

URL=$(gcloud run services describe "$SERVICE" --region "$REGION" --format 'value(status.url)')

schedule() {  # name, cron
  gcloud scheduler jobs delete "$1" --location "$REGION" --quiet >/dev/null 2>&1 || true
  gcloud scheduler jobs create http "$1" --location "$REGION" --schedule "$2" \
    --time-zone "${TIMEZONE:-Europe/London}" --uri "$URL/run/$1" --http-method POST \
    --headers "X-Token=$AUTOMATION_TOKEN,Content-Type=application/json" --message-body '{}'
}
schedule invoice_inbox "*/5 * * * *"
schedule meeting_reminders "0 8 * * *"

echo
echo "Deployed: $URL"
echo "Share your Drive folders, sheets and calendar with: $ACCOUNT"
echo "Zoom webhook (event: recording transcript completed): $URL/zoom"
echo "CRM webhook: POST $URL/run/client_folder with header X-Token and body {\"name\": ..., \"email\": ...}"

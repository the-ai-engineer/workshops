#!/usr/bin/env bash
# Email me when an automation fails.
#
# One alert rule covers every Cloud Run job and service in the project. It fires
# when any of them logs an error. The examples do that for you: when run() raises,
# the trigger prints one error line and the run is recorded as failed.
#
#   PROJECT=your-project-id ALERT_EMAIL=you@example.com ./alerts.sh
#
# NAMES is optional: a pattern for the job and service names to watch. Leave it
# out to watch everything in the project, or pass NAMES='^example-' to watch
# only the course examples.
set -euo pipefail

PROJECT="${PROJECT:?set PROJECT to your Google Cloud project id}"
EMAIL="${ALERT_EMAIL:?set ALERT_EMAIL to the address that should get the alerts}"
NAMES="${NAMES:-.*}"
RULE="An automation failed"

gcloud services enable monitoring.googleapis.com --project "$PROJECT"

# Where the alert goes. Reuse the email channel if this script already made it.
CHANNEL=$(gcloud beta monitoring channels list --project "$PROJECT" --format 'value(name,type,labels.email_address)' |
  awk -F'\t' -v email="$EMAIL" '$2 == "email" && $3 == email { print $1; exit }')
[ -n "$CHANNEL" ] || CHANNEL=$(gcloud beta monitoring channels create --project "$PROJECT" \
  --display-name "Automation alerts" --type email --channel-labels "email_address=$EMAIL" --format 'value(name)')

# When it fires: an error line from a Cloud Run job or service.
# At most one email every 5 minutes, however many errors there are.
POLICY=$(mktemp)
cat > "$POLICY" <<EOF
{
  "displayName": "$RULE",
  "combiner": "OR",
  "conditions": [{
    "displayName": "A Cloud Run job or service logged an error",
    "conditionMatchedLog": {
      "filter": "severity>=ERROR AND ((resource.type=\"cloud_run_job\" AND resource.labels.job_name=~\"$NAMES\") OR (resource.type=\"cloud_run_revision\" AND resource.labels.service_name=~\"$NAMES\"))"
    }
  }],
  "alertStrategy": {"notificationRateLimit": {"period": "300s"}, "autoClose": "1800s"},
  "notificationChannels": ["$CHANNEL"]
}
EOF

# Replace the rule if it is already there, so running this twice leaves one rule.
for old in $(gcloud monitoring policies list --project "$PROJECT" --filter "displayName=\"$RULE\"" --format 'value(name)'); do
  gcloud monitoring policies delete "$old" --project "$PROJECT" --quiet
done
gcloud monitoring policies create --project "$PROJECT" --policy-from-file "$POLICY" --format 'value(name)'
rm -f "$POLICY"

echo
echo "Alerts for failed automations go to $EMAIL."
echo "Test it: make a job fail, then check your inbox within a few minutes."

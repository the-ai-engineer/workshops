"""Meeting follow-up: after a client call on Zoom, a follow-up email is waiting in Gmail drafts.

Trigger: Zoom calls POST /zoom when a meeting's transcript is ready.
Steps: download the transcript, find the client's email on the calendar event
for that meeting, have Claude write a summary and a follow-up email, save the
summary to the Meetings sheet and the email to Gmail drafts. It saves a draft
rather than sending, so you read every client email before it goes.

Run it once by hand on a transcript file:
    uv run python -m automations.meeting_follow_up transcript.vtt "Acme kick-off" jo@acme.com
"""
import os
from datetime import date, datetime, timedelta

from pydantic import BaseModel, Field

from automations.meeting_reminders import guests_to_remind
from lib import google, mail, zoom
from lib.ai import extract


class FollowUp(BaseModel):
    summary: str = Field(description="What was discussed and decided, 3 to 5 sentences")
    next_steps: list[str] = Field(description="Who does what, one line each")
    email_subject: str
    email_body: str


def prompt(topic: str, transcript: str) -> str:
    return f"""You are writing for {os.environ.get("OWNER_NAME", "the business owner")} after a client call: "{topic}".

Write a summary of the call, the next steps, and a short follow-up email to the client.
The email thanks them, recaps what you agreed in a few lines, and says:
"{os.environ.get("FOLLOW_UP_PROMISE", "I'll follow up with the proposal in the next 48 hours.")}"
Plain, warm and short. Sign it with the owner's first name. Only state what the transcript supports.

Transcript:
{transcript}"""


def client_emails(meeting_id: str, start: str) -> list[str]:
    """External guests on the calendar event that holds this Zoom meeting."""
    around = datetime.fromisoformat(start.replace("Z", "+00:00"))
    events = google.events_between(os.environ["CALENDAR_ID"], (around - timedelta(hours=2)).isoformat(),
                                   (around + timedelta(hours=2)).isoformat())
    meeting_id = meeting_id.replace(" ", "")
    for event in events:
        text = (event.get("location", "") + event.get("description", "") + str(event.get("conferenceData", ""))).replace(" ", "")
        if meeting_id in text:
            return guests_to_remind(event, os.environ["OWN_DOMAIN"])
    return []


def follow_up(topic: str, transcript: str, to: list[str]) -> dict:
    result = extract(prompt(topic, transcript), FollowUp)
    google.append_row(os.environ["CLIENTS_SHEET_ID"], "Meetings", [
        date.today().isoformat(), topic, ", ".join(to), result.summary, "\n".join(result.next_steps),
    ])
    mail.save_draft(to, result.email_subject, result.email_body)
    return {"topic": topic, "to": to, **result.model_dump()}


def run(event: dict) -> dict:
    meeting = event["payload"]["object"]
    to = client_emails(str(meeting["id"]), meeting["start_time"])
    return follow_up(meeting["topic"], zoom.transcript(event), to)


if __name__ == "__main__":
    import sys

    from dotenv import load_dotenv

    load_dotenv()
    path, topic, *to = sys.argv[1:]
    print(follow_up(topic, zoom.vtt_to_text(open(path).read()), to))

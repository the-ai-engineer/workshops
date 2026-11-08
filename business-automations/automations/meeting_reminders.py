"""Meeting reminders: everyone outside the business gets a reminder the day before.

Trigger: Cloud Scheduler calls POST /run/meeting_reminders at 8am every day.
Steps: list tomorrow's events on the shared calendar, and email each guest
from outside OWN_DOMAIN who hasn't declined. No AI: not every automation needs it.

Run it once by hand:  uv run python -m automations.meeting_reminders
"""
import os
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from lib import google, mail


def reminder(event: dict, zone: ZoneInfo) -> tuple[str, str]:
    start = datetime.fromisoformat(event["start"]["dateTime"]).astimezone(zone)
    where = event.get("hangoutLink") or event.get("location") or "the link in your calendar invite"
    subject = f"Reminder: {event.get('summary', 'our meeting')} tomorrow at {start:%H:%M}"
    body = (f"Hi,\n\nA quick reminder that we're meeting tomorrow, {start:%A %d %B} at {start:%H:%M} "
            f"({zone.key}).\n\nJoin here: {where}\n\nSee you then.")
    return subject, body


def guests_to_remind(event: dict, own_domain: str) -> list[str]:
    return [
        guest["email"] for guest in event.get("attendees", [])
        if not guest["email"].endswith("@" + own_domain)
        and guest.get("responseStatus") != "declined"
        and not guest.get("resource")
    ]


def run(payload: dict | None = None) -> dict:
    zone = ZoneInfo(os.environ.get("TIMEZONE", "Europe/London"))
    own_domain = os.environ["OWN_DOMAIN"]
    day = date.fromisoformat((payload or {}).get("date") or (datetime.now(zone).date() + timedelta(days=1)).isoformat())
    start = datetime.combine(day, time.min, zone)
    end = start + timedelta(days=1)

    sent = []
    for event in google.events_between(os.environ["CALENDAR_ID"], start.isoformat(), end.isoformat()):
        if "dateTime" not in event["start"]:  # all-day events aren't meetings
            continue
        subject, body = reminder(event, zone)
        for guest in guests_to_remind(event, own_domain):
            mail.send(guest, subject, body)
            sent.append({"to": guest, "subject": subject})
    return {"date": day.isoformat(), "sent": sent}


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    print(run())

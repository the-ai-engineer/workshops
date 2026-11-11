"""04: speed to lead. Answer every website enquiry within a minute.

The client   a recruitment agency with an enquiry form on its website.
Today        enquiries sit in an inbox until the evening. By then the employer has called another agency.
Trigger      webhook. The website's form sends each enquiry to this automation.
Output       a row in the "Enquiries" tab with a reply already written, and a message to the team.

The steps never change, and one of them is a call to a model: writing the
reply. If that call fails the enquiry is still saved, because the one thing
this must never do is lose a lead.

    uv run python examples/04-speed_to_lead.py
    curl -X POST localhost:8080/hook -H "X-Token: $WEBHOOK_TOKEN" -H "Content-Type: application/json" \
      -d '{"name": "Sam Price", "email": "sam@example.com", "company": "Price Engineering", "message": "We need two site managers by January."}'
"""
from datetime import datetime

from pydantic import BaseModel

from toolkit import ai, sheets, triggers, web

TAB = "Enquiries"
BUSINESS = "a recruitment agency in South Wales"


class Enquiry(BaseModel):
    name: str
    email: str
    company: str = ""
    message: str


def run(payload: dict) -> dict:
    enquiry = Enquiry(**payload)

    # 1. Write a personal reply. If the model fails, carry on: the lead must not be lost.
    try:
        reply = ai.ask(
            f"You answer website enquiries for {BUSINESS}. Write a short reply to the enquiry below. "
            "Thank them by first name, show you read what they asked for, say a consultant will call them "
            "today, and ask one question that will help that call. Under 100 words, warm and plain. "
            "Do not promise prices, dates or candidates. Reply with the message only.\n\n"
            f"Name: {enquiry.name}\nCompany: {enquiry.company or 'not given'}\nMessage: {enquiry.message}"
        ).strip()
        status = "reply drafted"
    except Exception:
        reply, status = "", "needs a reply"

    # 2. Save the enquiry and the reply. A person reads the reply before it is sent.
    sheets.add(TAB, [datetime.now().isoformat(timespec="minutes"), enquiry.name, enquiry.email,
                     enquiry.company, enquiry.message, reply, status])

    # 3. Tell the team.
    told = web.notify(f"New enquiry from {enquiry.name} ({enquiry.company or enquiry.email}): {status}.")

    return {"status": status, "team_told": told, "reply": reply}


if __name__ == "__main__":
    triggers.webhook(run)

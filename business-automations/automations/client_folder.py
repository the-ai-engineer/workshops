"""Client folder: a new client in the CRM gets a Drive folder.

Trigger: the CRM's webhook (HubSpot, Pipedrive, Airtable, a form) calls
POST /run/client_folder with the client's name and email.
Steps: create the client's folder and its subfolders, then add the client and
the folder link to the Clients sheet. If the folder already exists, nothing
changes, so a webhook that fires twice is harmless.

Run it once by hand:  uv run python -m automations.client_folder "Acme Ltd" jo@acme.com
"""
import os
from datetime import date

from pydantic import BaseModel, EmailStr

from lib import google

SUBFOLDERS = ["Contracts", "Invoices", "Meeting notes", "Shared with client"]


class Client(BaseModel):
    name: str
    email: EmailStr


def run(payload: dict) -> dict:
    client = Client(**payload)
    parent = os.environ["CLIENTS_FOLDER_ID"]

    existing = google.find_folder(parent, client.name)
    if existing:
        return {"created": False, "folder": existing["webViewLink"]}

    folder = google.create_folder(parent, client.name)
    for name in SUBFOLDERS:
        google.create_folder(folder["id"], name)
    google.append_row(os.environ["CLIENTS_SHEET_ID"], "Clients",
                      [date.today().isoformat(), client.name, client.email, folder["webViewLink"]])
    return {"created": True, "folder": folder["webViewLink"]}


if __name__ == "__main__":
    import sys

    from dotenv import load_dotenv

    load_dotenv()
    print(run({"name": sys.argv[1], "email": sys.argv[2]}))

"""Invoice inbox: a PDF dropped in a Drive folder becomes a row in a Google Sheet.

Trigger: Cloud Scheduler calls POST /run/invoice_inbox every 5 minutes.
Steps: list the Inbox folder, read each PDF with Claude, add a row to the
Invoices sheet, move the PDF to Processed. A file in Processed is done, so a
rerun never adds the same invoice twice.

Run it once by hand:  uv run python -m automations.invoice_inbox
"""
import os
from datetime import date

from pydantic import BaseModel, Field

from lib import google
from lib.ai import extract


class Invoice(BaseModel):
    supplier: str
    invoice_number: str | None
    invoice_date: str | None = Field(description="YYYY-MM-DD")
    due_date: str | None = Field(description="YYYY-MM-DD")
    currency: str = Field(description="ISO code, e.g. GBP")
    total: float = Field(description="Amount due, including tax")


PROMPT = "Read this invoice and fill in the fields. Use null for anything the invoice doesn't show."


def process(file: dict, inbox: str, processed: str, sheet: str) -> dict:
    invoice = extract(PROMPT, Invoice, pdf=google.download(file["id"]))
    google.append_row(sheet, "Invoices", [
        date.today().isoformat(),
        invoice.supplier,
        invoice.invoice_number or "",
        invoice.invoice_date or "",
        invoice.due_date or "",
        invoice.currency,
        invoice.total,
        file["webViewLink"],
    ])
    google.move(file["id"], inbox, processed)
    return {"file": file["name"], **invoice.model_dump()}


def run(payload: dict | None = None) -> dict:
    inbox = os.environ["INBOX_FOLDER_ID"]
    processed = os.environ["PROCESSED_FOLDER_ID"]
    sheet = os.environ["INVOICES_SHEET_ID"]

    done, failed = [], []
    for file in google.list_files(inbox):
        if file["mimeType"] != "application/pdf":
            continue
        try:
            done.append(process(file, inbox, processed, sheet))
        except Exception as error:  # one bad file shouldn't stop the rest; it stays in Inbox for the next run
            failed.append({"file": file["name"], "error": str(error)})
    return {"processed": done, "failed": failed}


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    print(run())

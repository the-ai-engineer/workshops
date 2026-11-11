"""05: receipts. Drop a receipt in a folder and it becomes a row in a spreadsheet.

The client   wants expenses in the books without typing.
Today        receipts pile up as photos and PDFs and get typed in at month end, with mistakes.
Trigger      scheduled. Every few minutes it checks a Drive folder for files it has not handled.
Output       a row in the "Expenses" tab for each new receipt.

The steps never change, and one of them is a call to a model: reading the
receipt. Every receipt needs the same fields, so this is one call, not an agent.

    uv run python examples/05-receipts.py
"""
import os
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from toolkit import ai, drive, sheets, triggers

TAB = "Expenses"


class Receipt(BaseModel):
    merchant: str
    date: str = Field(description="The date on the receipt, YYYY-MM-DD, or 'unknown'")
    total: float = Field(description="The amount paid, including tax")
    currency: str = Field(description="ISO code, such as GBP")
    category: Literal["Travel", "Meals", "Software", "Office", "Other"]


def run() -> dict:
    saved, failed = [], []
    for file in drive.new_files(os.environ["RECEIPTS_FOLDER_ID"], "application/pdf", "image/"):
        try:
            # 1. Read the receipt.
            receipt = ai.ask("Read this receipt and fill in the fields.", shape=Receipt,
                             file=(drive.download(file["id"]), file["mimeType"]))
            # 2. Add the row.
            sheets.add(TAB, [str(date.today()), receipt.merchant, receipt.date, receipt.total,
                             receipt.currency, receipt.category, file["webViewLink"]])
            # 3. Mark the file as done, so the next run skips it.
            drive.mark_done(file["id"])
            saved.append(file["name"])
        except Exception as error:  # one bad file must not stop the rest
            failed.append(f"{file['name']}: {error}")

    if failed:  # fail the run, so the alert fires and a person looks at the files left behind
        raise RuntimeError(f"saved {len(saved)}, could not read {len(failed)}: {'; '.join(failed)}")
    return {"saved": saved}


if __name__ == "__main__":
    triggers.job(run)

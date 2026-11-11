"""00: an automation with no AI.

Trigger: a schedule (cron, Cloud Scheduler). Each run handles whatever is new.
Input:   a signed contract dropped in the Contracts inbox folder in Drive,
         named "<Client name> - <anything>.pdf", e.g. "Acme Ltd - contract.pdf".
Steps:   read the client's name from the file name, find the client's folder,
         add a row to the Contracts tab of the CRM sheet, move the file there.
Output:  the contract is filed under the client and the CRM shows it.

Every step is a rule, so the same input gives the same result every time.
A contract for a client with no folder stays in the inbox for a person to look at.

    uv run python src/00-contract_filing.py
"""
import json
import os
from datetime import date

import tools


def process(contract: dict, inbox: str) -> dict:
    client = contract["name"].split(" - ")[0].strip()
    folder = tools.find_folder(os.environ["CLIENTS_FOLDER_ID"], client)
    if folder is None:
        return {"file": contract["name"], "status": "skipped", "why": f"no client folder called {client}"}

    tools.add_row(os.environ["CLIENTS_SHEET_ID"], "Contracts",
                  [date.today().isoformat(), client, contract["name"], contract["webViewLink"]])
    contracts = tools.find_folder(folder["id"], "Contracts") or folder
    tools.move_file(contract["id"], inbox, contracts["id"])  # out of the inbox, so the next run won't see it
    return {"file": contract["name"], "status": "filed", "client": client}


def run() -> list[dict]:
    inbox = os.environ["CONTRACTS_INBOX_ID"]
    return [process(contract, inbox) for contract in tools.new_files(inbox, "application/pdf")]


if __name__ == "__main__":
    for result in run():
        print(json.dumps(result))

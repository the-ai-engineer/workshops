"""01: a simple automation. Fixed steps, one AI call.

Trigger: a schedule (Cloud Scheduler, once a day).
Input:   a search, e.g. "recruitment companies in South Wales".
Steps:   1. read the leads already in the sheet     code
         2. search Google for companies not on it   one model call
         3. drop any the sheet already has          code
         4. add the rest as rows                    code
Output:  new rows in the Leads tab of the CRM sheet, a few more every day.

The code decides the order and it never changes. The model does the one step
that needs it, and has to answer in a fixed shape (the Lead class), so the
rest is plain code. Empty the Leads tab, run it, and watch the rows appear.

    uv run python src/01-lead_research.py
"""
import json
import os
from datetime import date

from pydantic import BaseModel, Field

import tools

QUERY = os.environ.get("LEADS_QUERY", "recruitment companies in South Wales")
PER_RUN = int(os.environ.get("LEADS_PER_RUN", "10"))


class Lead(BaseModel):
    name: str
    website: str = Field(description="The company's own website, taken from the search results")
    town: str
    specialism: str = Field(description="What they do, in a few words")


class Leads(BaseModel):
    leads: list[Lead]


def run() -> dict:
    sheet = os.environ["CLIENTS_SHEET_ID"]
    # Every name in column B, header included. That way the tab can be emptied, header and all, for a demo.
    known = {row[1].strip().lower() for row in tools.read_rows(sheet, "Leads") if len(row) > 1}

    found = tools.research(
        f"Search Google for {QUERY}. List {PER_RUN} real companies that have their own website."
        f" Leave out these, which we already have: {', '.join(sorted(known)) or 'none'}.",
        Leads,
    ).leads

    added = []
    for lead in found:
        if lead.name.strip().lower() in known:  # the model was told to skip these; the code makes sure
            continue
        known.add(lead.name.strip().lower())
        tools.add_row(sheet, "Leads", [date.today().isoformat(), lead.name, lead.website, lead.town, lead.specialism])
        added.append(lead.name)
    return {"query": QUERY, "status": "done", "added": added, "skipped": len(found) - len(added)}


if __name__ == "__main__":
    print(json.dumps(run()))

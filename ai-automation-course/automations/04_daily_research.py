"""04: daily research. Every morning, which companies in our market just showed a reason to buy?

The business   any B2B company with a sales team. A company that just raised money, hired a new
               leader or opened a new site is far more likely to buy than one picked from a list.
Today          someone spends the first hour of the day searching the news, and misses most of it.
Trigger        scheduled, every weekday at 7am.
Output         new rows in the "Prospects" tab of the sales team's sheet, and one Slack message.

The steps are fixed and only one needs judgment: reading the search results.
That is one model call, and the model has to answer in a fixed shape (the
Prospect class). Everything after it is plain code, so the code, not the model,
decides what counts as new and what gets saved.

Change MARKET and SIGNALS to fit the business.

    uv run python automations/04_daily_research.py
"""
from datetime import date

from pydantic import BaseModel, Field

from toolkit import ai, sheets, slack, triggers

TAB = "Prospects"
MARKET = "UK logistics and warehousing companies with 50 to 1,000 staff"
SIGNALS = [
    "raised investment or was acquired",
    "hired a new operations, technology or finance leader",
    "opened a new site or won a large contract",
]


class Prospect(BaseModel):
    company: str
    signal: str = Field(description="What happened, in one sentence")
    source: str = Field(description="Link to the article or post, copied from the search results")
    published: str = Field(description="When it was published, YYYY-MM-DD, or 'unknown'")


class Found(BaseModel):
    prospects: list[Prospect]


def find(signal: str, known: str) -> list[Prospect]:
    """The one step that needs judgment: search, read the results and pick out real prospects."""
    found = ai.ask(
        f"Today is {date.today()}. Search Google for {MARKET} that {signal} in the last 7 days. "
        "List up to 5. Only include companies you found in the search results, with the link you found "
        f"them at. Leave out these companies, which we already have: {known or 'none'}.",
        shape=Found,
        search=True,
    )
    return found.prospects


def run() -> dict:
    # 1. What do we already have? The code checks, so a repeat never reaches the sheet.
    rows = sheets.read(TAB)
    have = {row[1].strip().lower() for row in rows if len(row) > 1}  # every row, so it works with or without a header
    known = ", ".join(row[1] for row in rows[-100:] if len(row) > 1)

    # 2. Search once per signal, then 3. save the new ones.
    added = []
    for signal in SIGNALS:
        for prospect in find(signal, known):
            name = prospect.company.strip()
            if name.lower() in have or not prospect.source.startswith("http"):
                continue  # already have it, or no link to check it against
            have.add(name.lower())
            sheets.add(TAB, [str(date.today()), name, prospect.signal, prospect.published, prospect.source, "new"])
            added.append(name)

    # 4. One message for the team, only when there is something to read.
    if added:
        slack.post(f"{len(added)} new prospects in the sheet today: {', '.join(added)}")
    return {"added": added}


if __name__ == "__main__":
    triggers.job(run)

"""03: job leads. Every morning, which local companies started hiring?

The client   a recruitment agency. A company that has just advertised a job is their best lead.
Today        a junior spends the first hour of the day on job boards, and misses most of them.
Trigger      scheduled, every day at 9am.
Output       new rows in the "Job leads" tab of the sheet.

The steps never change, and one of them is a call to a model. The model has to
answer in a fixed shape (the Job class), so the steps after it are plain code.

    uv run python examples/03-job_leads.py
"""
from datetime import date

from pydantic import BaseModel, Field

from toolkit import ai, sheets, triggers, web

SEARCH = "accountancy and finance jobs in South Wales"
TAB = "Job leads"


class Job(BaseModel):
    employer: str = Field(description="The company that is hiring. Not a recruitment agency or a job board")
    title: str
    town: str
    posted: str = Field(description="The date the advert was posted, YYYY-MM-DD, or 'unknown'")
    link: str = Field(description="Link to the advert, taken from the search results")


class Jobs(BaseModel):
    jobs: list[Job]


def run() -> dict:
    # 1. What do we already have?
    rows = sheets.read(TAB)
    have = {(row[1].lower(), row[2].lower()) for row in rows if len(row) > 2}
    recent = "; ".join(f"{row[1]}, {row[2]}" for row in rows[-50:] if len(row) > 2)

    # 2. Ask the model to search for new adverts.
    found = ai.ask(
        f"Today is {date.today()}. Search Google for {SEARCH}, advertised in the last 7 days by the employer "
        "itself, not by a recruitment agency. List up to 10. Only include adverts you found in the search "
        f"results. Leave out these, which we already have: {recent or 'none'}.",
        shape=Jobs,
        search=True,
    )

    # 3. Save the ones that are new. The model was told to skip repeats; the code makes sure.
    added = []
    for job in found.jobs:
        if (job.employer.lower(), job.title.lower()) in have:
            continue
        have.add((job.employer.lower(), job.title.lower()))
        sheets.add(TAB, [str(date.today()), job.employer, job.title, job.town, job.posted, web.follow(job.link)])
        added.append(f"{job.employer}: {job.title}")

    return {"added": added}


if __name__ == "__main__":
    triggers.job(run)

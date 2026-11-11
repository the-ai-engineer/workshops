"""06: video to content. An agent turns a video into the posts that suit it.

The client   wants more than one post out of each video they record.
Today        a video goes out once. Nobody has the hour it takes to rewrite it.
Trigger      scheduled. Every few minutes it checks a Drive folder for videos it has not handled.
Output       rows in the "Content" tab: one draft for each format the agent chose.

There is no fixed order of steps here. The agent decides which formats suit
the video, so a two-minute clip and a forty-minute talk get different things.
What keeps it safe is in the tools, not in the prompt:
  - the tools only reach this one video
  - save_draft refuses a format that is not in FORMATS, and never saves the same draft twice
  - the agent is stopped after max_turns calls to the model
A person reviews every draft before it is posted.

    uv run python examples/06-video_to_content.py
"""
import os
from datetime import date

from toolkit import ai, drive, sheets, triggers

TAB = "Content"

# One line per format the agent may write. Adding a format is adding a line.
FORMATS = {
    "Reel script": "Instagram Reel script, under 45 seconds: a hook, three beats, a call to action.",
    "LinkedIn post": "LinkedIn post under 200 words. The first line is the hook.",
    "Newsletter": "Newsletter draft: a subject line, an intro and three short sections.",
}

INSTRUCTION = """You turn a video into written content drafts.

Get the transcript once. Then choose the formats that suit this video: a short clip may only
carry a Reel script, a long talk can carry all of them. Skip a format when the video has too
little in it to fill that format well. Check which drafts already exist and do not write those again.
Use only what the transcript says.

Finish with one line per draft you saved and one line per format you skipped, with the reason.

Formats:
""" + "\n".join(f"- {name}: {rule}" for name, rule in FORMATS.items())


def make_content(video: dict) -> dict:
    # The agent's tools. They are tied to this one video, so it cannot touch anything else.

    def get_transcript() -> str:
        """The words spoken in the video."""
        return ai.transcribe(drive.download(video["id"]))

    def existing_drafts() -> list[str]:
        """The formats already drafted for this video."""
        return [row[2] for row in sheets.read(TAB) if len(row) > 2 and row[1] == video["name"]]

    def save_draft(format: str, text: str) -> str:
        """Save one draft. `format` must be one of the listed formats."""
        if format not in FORMATS:
            return f"Refused: {format} is not a format. Use one of: {', '.join(FORMATS)}."
        if format in existing_drafts():
            return "Not saved: this video already has a draft in that format."
        sheets.add(TAB, [str(date.today()), video["name"], format, text])
        return "Saved."

    report = ai.agent(INSTRUCTION, f"New video: {video['name']}",
                      tools=[get_transcript, existing_drafts, save_draft], max_turns=10)
    drive.mark_done(video["id"])  # only once the agent has finished, so a failed run is tried again
    return {"video": video["name"], "drafts": existing_drafts(), "report": report}


def run() -> dict:
    videos = drive.new_files(os.environ["VIDEOS_FOLDER_ID"], "video/")
    return {"videos": [make_content(video) for video in videos]}


if __name__ == "__main__":
    triggers.job(run)

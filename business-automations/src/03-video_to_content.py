"""03: the agent orchestrates, the tools are code.

Trigger: a schedule. Each run handles whatever is new.
Input:   a video dropped in the Videos folder in Drive.
Steps:   the agent decides. It has three tools: get the transcript, see which
         drafts exist, save a draft.
Output:  the transcript in the Transcripts tab and one row in the Content tab
         per format the agent chose. A person reviews every draft before it is posted.

There is no fixed order here. The agent picks the formats that suit the video,
so a two-minute clip and a forty-minute talk take different paths. What keeps
it safe is in the tools, not the prompt:
  - the tools only reach this one video
  - save_draft refuses a format that isn't in FORMATS and never saves a draft twice
  - the loop stops after max_turns
The code still owns the trigger and marks the video as handled.

    uv run python src/03-video_to_content.py
"""
import json
import os

import tools
from agent import run_agent

# One line per format the agent may write. Adding a format is adding a line.
FORMATS = {
    "Reel script": "Instagram Reel script, under 45 seconds: a hook, three beats, a call to action.",
    "LinkedIn post": "LinkedIn post under 200 words. The first line is the hook.",
    "Newsletter": "Newsletter draft: a subject line, an intro and three short sections.",
}

INSTRUCTION = """You turn a video into written content drafts.

Get the transcript first. Then choose the formats that suit this video: a short clip
may only carry a Reel script, a long talk can carry all of them. Skip a format when
the video has too little in it to fill that format well.
Check which drafts already exist and do not write those again.
Use only what the transcript says.

Finish with one line per draft you saved and one line per format you skipped, with the reason.

Formats:
""" + "\n".join(f"- {name}: {rule}" for name, rule in FORMATS.items())


def process(video: dict) -> dict:
    sheet, name = os.environ["CLIENTS_SHEET_ID"], video["name"]

    # The agent's tools, tied to this one video. It can't name another file.

    def get_transcript() -> str:
        """The video's transcript, word for word. Also saves it to the Transcripts tab."""
        transcript = tools.transcribe(video["id"])
        tools.save_once(sheet, "Transcripts", [name], transcript)
        return transcript

    def existing_drafts() -> list[str]:
        """The formats already drafted for this video."""
        return [row[2] for row in tools.read_rows(sheet, "Content") if len(row) > 2 and row[1] == name]

    def save_draft(format: str, text: str) -> str:
        """Save one content draft to the Content tab. `format` must be one of the listed formats."""
        if format not in FORMATS:
            return f"Refused: {format} is not a format. Use one of: {', '.join(FORMATS)}."
        saved = tools.save_once(sheet, "Content", [name, format], text)
        return "Saved." if saved else "Not saved: this video already has a draft in that format."

    report = run_agent(INSTRUCTION, f"New video: {name}", [get_transcript, existing_drafts, save_draft], max_turns=10)
    tools.mark_handled(video["id"])  # only after the agent finished; if it didn't, the next run tries again
    return {"file": name, "status": "done", "drafts": existing_drafts(), "report": report}


def run() -> list[dict]:
    results = []
    for video in tools.new_files(os.environ["VIDEOS_FOLDER_ID"], "video/"):
        try:
            results.append(process(video))
        except Exception as error:  # one bad video shouldn't stop the rest
            results.append({"file": video["name"], "status": "error", "error": str(error)})
    return results


if __name__ == "__main__":
    for result in run():
        print(json.dumps(result))

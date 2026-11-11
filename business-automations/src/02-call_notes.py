"""02: a workflow with one agent step.

Trigger: a schedule. Each run handles whatever is new.
Input:   a call recording (audio or video) dropped in the Recordings folder in Drive.
Steps:   1. transcribe it                                 one model call
         2. save the transcript to the Transcripts tab    code
         3. write the call notes                          AGENT
         4. save the notes to the Call notes tab          code
         5. mark the recording as handled                 code
Output:  a row in the Transcripts tab and a row in the Call notes tab of the CRM sheet.

The code decides the order. Only step 3 is open-ended: the agent works out
which client the call was with and what was promised on earlier calls, using
two tools it can call as it sees fit. It is fenced in: two read-only tools, a
turn limit, and if it fails the transcript is still saved.

    uv run python src/02-call_notes.py
"""
import json
import os

import tools
from agent import run_agent

INSTRUCTION = """You write call notes for a small business.

Work out which client the call was with. Check the client list and use the name exactly
as it is listed. If no client on the list fits, say "Client: unknown".
Then look up the notes from earlier calls with that client to see what was promised.

Write:
Client: <name>
Summary: what was discussed and decided, 3 to 5 sentences.
Next steps: who does what, one line each.
Still open: anything promised on an earlier call that this call did not close.

Only state what the transcript and the earlier notes support."""


# The agent's tools. Both only read, so the worst a wrong call can do is waste a turn.

def list_clients() -> list[str]:
    """The name of every client in the CRM."""
    rows = tools.read_rows(os.environ["CLIENTS_SHEET_ID"], "Clients")[1:]  # the first row is the header
    return [row[1] for row in rows if len(row) > 1]


def past_notes(client: str) -> list[str]:
    """Notes from the last three calls with this client, oldest first."""
    rows = tools.read_rows(os.environ["CLIENTS_SHEET_ID"], "Call notes")
    return [f"{row[0]}: {row[2]}" for row in rows if len(row) > 2 and f"client: {client}".lower() in row[2].lower()][-3:]


def process(recording: dict) -> dict:
    sheet, name = os.environ["CLIENTS_SHEET_ID"], recording["name"]
    transcript = tools.transcribe(recording["id"])
    tools.save_once(sheet, "Transcripts", [name], transcript)
    try:
        notes = run_agent(INSTRUCTION, f"Transcript of {name}:\n\n{transcript}",
                          [list_clients, past_notes], max_turns=6)
    except Exception as error:  # the agent step never blocks the fixed steps
        notes = f"Notes skipped: {error}"
    tools.save_once(sheet, "Call notes", [name], notes)
    tools.mark_handled(recording["id"])
    return {"file": name, "status": "done", "notes": notes}


def run() -> list[dict]:
    results = []
    for recording in tools.new_files(os.environ["RECORDINGS_FOLDER_ID"], "audio/", "video/"):
        try:
            results.append(process(recording))
        except Exception as error:  # one bad recording shouldn't stop the rest
            results.append({"file": recording["name"], "status": "error", "error": str(error)})
    return results


if __name__ == "__main__":
    for result in run():
        print(json.dumps(result))

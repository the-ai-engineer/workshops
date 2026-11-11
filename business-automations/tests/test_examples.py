"""The step-by-step examples in src/ against fake Drive, Sheets and Gemini, so the tests need no keys."""
import importlib.util
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from google.genai import types

SRC = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(SRC))  # the examples import tools.py and agent.py from their own folder

import agent  # noqa: E402
import tools  # noqa: E402


def load(name: str):
    """Import an example by file name: "01-lead_research" can't be imported the usual way."""
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), SRC / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


no_ai, simple = load("00-contract_filing"), load("01-lead_research")
agent_node, orchestrates = load("02-call_notes"), load("03-video_to_content")
webhook = load("04-webhook_to_sheet")


@pytest.fixture(autouse=True)
def env(monkeypatch):
    for key, value in {
        "CONTRACTS_INBOX_ID": "inbox", "CLIENTS_FOLDER_ID": "clients", "CLIENTS_SHEET_ID": "crm",
        "RECORDINGS_FOLDER_ID": "recordings", "VIDEOS_FOLDER_ID": "videos", "WEBHOOK_TOKEN": "secret",
    }.items():
        monkeypatch.setenv(key, value)


class FakeTools:
    def __init__(self, files=(), folders=(), sheet=None, found=()):
        self.files, self.folders, self.sheet, self.found = list(files), dict(folders), dict(sheet or {}), list(found)
        self.rows, self.moved, self.handled = [], [], []

    def new_files(self, folder_id, *types):
        return [file for file in self.files if file["mimeType"].startswith(types)]

    def find_folder(self, parent_id, name):
        return self.folders.get((parent_id, name))

    def move_file(self, file_id, from_folder, to_folder):
        self.moved.append((file_id, from_folder, to_folder))

    def add_row(self, sheet_id, tab, row):
        self.rows.append((tab, row))

    def read_rows(self, sheet_id, tab):
        return self.sheet.get(tab, [])

    def research(self, question, schema):
        self.question = question
        return schema(leads=self.found)

    def transcribe(self, file_id):
        if file_id == "broken":
            raise ValueError("no audio")
        return f"transcript of {file_id}"

    def save_once(self, sheet_id, tab, key, text):
        if any(row[1:1 + len(key)] == key for row in self.read_rows(sheet_id, tab)):
            return False
        self.sheet.setdefault(tab, []).append(["today", *key, text])
        return True

    def mark_handled(self, file_id):
        self.handled.append(file_id)


def file(file_id, name, mime):
    return {"id": file_id, "name": name, "mimeType": mime, "webViewLink": f"https://drive/{file_id}"}


# 00

def test_no_ai_files_a_contract_under_its_client(monkeypatch):
    fake = FakeTools(
        files=[file("a", "Acme Ltd - contract.pdf", "application/pdf"),
               file("b", "Nobody - contract.pdf", "application/pdf"),
               file("c", "notes.txt", "text/plain")],
        folders={("clients", "Acme Ltd"): {"id": "acme"}, ("acme", "Contracts"): {"id": "acme-contracts"}},
    )
    monkeypatch.setattr(no_ai, "tools", fake)

    results = no_ai.run()

    assert [result["status"] for result in results] == ["filed", "skipped"]
    assert fake.moved == [("a", "inbox", "acme-contracts")]
    assert [(tab, row[1:]) for tab, row in fake.rows] == [
        ("Contracts", ["Acme Ltd", "Acme Ltd - contract.pdf", "https://drive/a"])]


# 01

def lead(name):
    return {"name": name, "website": f"https://{name.lower()}.example", "town": "Cardiff", "specialism": "IT"}


def test_simple_adds_only_the_leads_the_sheet_does_not_have(monkeypatch):
    fake = FakeTools(sheet={"Leads": [["Date", "Name"], ["2026-11-10", "Acorn"]]},
                     found=[lead("Acorn"), lead("Birch"), lead("birch "), lead("Cedar")])
    monkeypatch.setattr(simple, "tools", fake)

    result = simple.run()

    assert result["added"] == ["Birch", "Cedar"] and result["skipped"] == 2
    assert "acorn" in fake.question  # the model is told what the sheet already has
    assert [(tab, row[1:]) for tab, row in fake.rows] == [
        ("Leads", ["Birch", "https://birch.example", "Cardiff", "IT"]),
        ("Leads", ["Cedar", "https://cedar.example", "Cardiff", "IT"])]


# 02

def test_agent_node_saves_the_transcript_and_the_agents_notes(monkeypatch):
    fake = FakeTools(
        files=[file("r1", "kickoff.mp4", "video/mp4"), file("broken", "bad.m4a", "audio/mp4")],
        sheet={"Clients": [["Date", "Name", "Email"], ["2026-11-01", "Acme Ltd", "jo@acme.com"]],
               "Call notes": [["2026-11-02", "intro.mp4", "Client: Acme Ltd\nSummary: said hello"],
                              ["2026-11-03", "other.mp4", "Client: Zed\nSummary: mentions Acme Ltd"]]},
    )
    monkeypatch.setattr(agent_node, "tools", fake)
    seen = {}

    def fake_agent(instruction, task, tools, max_turns):
        seen["task"], seen["tools"] = task, [tool.__name__ for tool in tools]
        client = tools[0]()[0]
        return f"Client: {client}\nEarlier: {tools[1](client)}"

    monkeypatch.setattr(agent_node, "run_agent", fake_agent)

    results = agent_node.run()

    assert [result["status"] for result in results] == ["done", "error"]
    assert seen["tools"] == ["list_clients", "past_notes"]
    assert "transcript of r1" in seen["task"]
    assert fake.sheet["Transcripts"] == [["today", "kickoff.mp4", "transcript of r1"]]
    notes = fake.sheet["Call notes"][-1]
    assert notes[1] == "kickoff.mp4"
    assert notes[2].startswith("Client: Acme Ltd") and "said hello" in notes[2] and "Zed" not in notes[2]
    assert fake.handled == ["r1"]  # the broken recording stays for the next run


def test_agent_node_keeps_the_transcript_when_the_agent_fails(monkeypatch):
    fake = FakeTools(files=[file("r1", "kickoff.mp4", "video/mp4")])
    monkeypatch.setattr(agent_node, "tools", fake)

    def failing_agent(*args, **kwargs):
        raise RuntimeError("the agent did not finish in 6 turns")

    monkeypatch.setattr(agent_node, "run_agent", failing_agent)

    agent_node.run()

    assert fake.sheet["Transcripts"][0][1:] == ["kickoff.mp4", "transcript of r1"]
    assert fake.sheet["Call notes"][0][2] == "Notes skipped: the agent did not finish in 6 turns"
    assert fake.handled == ["r1"]


# 03

def test_agent_orchestrates_with_tools_that_hold_the_guardrails(monkeypatch):
    fake = FakeTools(files=[file("v1", "talk.mp4", "video/mp4")],
                     sheet={"Content": [["2026-11-01", "other.mp4", "Newsletter", "someone else's draft"]]})
    monkeypatch.setattr(orchestrates, "tools", fake)
    replies = []

    def fake_agent(instruction, task, tools, max_turns):
        get_transcript, existing_drafts, save_draft = tools
        transcript = get_transcript()
        replies.append(existing_drafts())
        replies.append(save_draft("Reel script", f"reel from {transcript}"))
        replies.append(save_draft("Reel script", "a second copy"))
        replies.append(save_draft("Tweet", "not a listed format"))
        return f"Wrote {existing_drafts()}"

    monkeypatch.setattr(orchestrates, "run_agent", fake_agent)

    result = orchestrates.run()[0]

    assert replies[0] == []  # another video's drafts are not this video's
    assert replies[1] == "Saved." and replies[2].startswith("Not saved") and replies[3].startswith("Refused")
    assert result["drafts"] == ["Reel script"]
    assert fake.sheet["Content"][-1] == ["today", "talk.mp4", "Reel script", "reel from transcript of v1"]
    assert fake.sheet["Transcripts"] == [["today", "talk.mp4", "transcript of v1"]]
    assert fake.handled == ["v1"]


def test_agent_orchestrates_leaves_the_video_for_the_next_run_when_the_agent_fails(monkeypatch):
    fake = FakeTools(files=[file("v1", "talk.mp4", "video/mp4")])
    monkeypatch.setattr(orchestrates, "tools", fake)

    def failing_agent(*args, **kwargs):
        raise RuntimeError("the agent did not finish in 10 turns")

    monkeypatch.setattr(orchestrates, "run_agent", failing_agent)

    assert orchestrates.run()[0]["status"] == "error"
    assert fake.handled == []


# 04

def test_webhook_checks_the_token_then_adds_a_row(monkeypatch):
    fake = FakeTools()
    monkeypatch.setattr(webhook, "tools", fake)
    client = TestClient(webhook.app)

    assert client.post("/hook", json={"name": "Owain"}).status_code == 401
    assert client.post("/hook", json={"name": "Owain"}, headers={"X-Token": "wrong"}).status_code == 401
    assert fake.rows == []

    reply = client.post("/hook", json={"name": "Owain"}, headers={"X-Token": "secret"})

    assert reply.json() == {"message": "Hello, Owain!"}
    assert [(tab, row[1:]) for tab, row in fake.rows] == [("Webhook", ["Owain", '{"name": "Owain"}'])]


# The agent loop

class FakeGemini:
    """Replies with a script: each item is a tool call (name, args) or the final text."""

    def __init__(self, script):
        self.script, self.requests = list(script), []
        self.models = self

    def generate_content(self, model, contents, config):
        self.requests.append(list(contents))
        step = self.script.pop(0)
        part = types.Part(text=step) if isinstance(step, str) else types.Part(
            function_call=types.FunctionCall(name=step[0], args=step[1]))
        return types.GenerateContentResponse(
            candidates=[types.Candidate(content=types.Content(role="model", parts=[part]))],
            usage_metadata=types.GenerateContentResponseUsageMetadata(total_token_count=10),
        )


def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


def test_agent_loop_runs_the_tools_the_model_asks_for(monkeypatch):
    fake = FakeGemini([("add", {"a": 2, "b": 3}), ("add", {"a": "x"}), "The answer is 5."])
    monkeypatch.setattr(tools, "gemini", lambda: fake)

    assert agent.run_agent("Be brief.", "What is 2 + 3?", [add]) == "The answer is 5."

    results = [content.parts[0].function_response.response["result"] for content in fake.requests[-1][2::2]]
    assert results[0] == 5
    assert results[1].startswith("Error:")  # a failed tool call goes back to the model, it doesn't crash the run


def test_agent_loop_stops_at_the_turn_limit(monkeypatch):
    fake = FakeGemini([("add", {"a": 1, "b": 1})] * 5)
    monkeypatch.setattr(tools, "gemini", lambda: fake)

    with pytest.raises(RuntimeError, match="did not finish in 3 turns"):
        agent.run_agent("Be brief.", "Loop forever.", [add], max_turns=3)
    assert len(fake.requests) == 3


# tools.save_once

def test_save_once_never_saves_the_same_key_twice(monkeypatch):
    sheet = {"Content": [["Date", "Video", "Format", "Draft"]]}
    monkeypatch.setattr(tools, "read_rows", lambda sheet_id, tab: sheet[tab])
    monkeypatch.setattr(tools, "add_row", lambda sheet_id, tab, row: sheet[tab].append(row))

    assert tools.save_once("crm", "Content", ["talk.mp4", "Newsletter"], "x" * 60_000) is True
    assert tools.save_once("crm", "Content", ["talk.mp4", "Newsletter"], "again") is False
    assert tools.save_once("crm", "Content", ["talk.mp4", "Reel script"], "reel") is True
    assert [row[1:3] for row in sheet["Content"][1:]] == [["talk.mp4", "Newsletter"], ["talk.mp4", "Reel script"]]
    assert len(sheet["Content"][1][3]) == tools.MAX_CELL  # a cell can't hold more

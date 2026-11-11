"""The course examples in examples/ against fake Sheets and a fake model, so the tests need no keys."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

EXAMPLES = Path(__file__).parent.parent / "examples"
sys.path.insert(0, str(EXAMPLES))  # the examples import the toolkit from their own folder

from toolkit import ai, drive, sheets, triggers, web  # noqa: E402


def load(name: str):
    """Import an example by file name: "01-hello_job" can't be imported the usual way."""
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), EXAMPLES / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hello_job, hello_webhook, job_leads = load("01-hello_job"), load("02-hello_webhook"), load("03-job_leads")
speed_to_lead, receipts, video = load("04-speed_to_lead"), load("05-receipts"), load("06-video_to_content")


@pytest.fixture
def sheet(monkeypatch):
    """A fake sheet: tab name -> rows."""
    tabs = {}
    monkeypatch.setattr(sheets, "read", lambda tab: tabs.get(tab, []))
    monkeypatch.setattr(sheets, "add", lambda tab, row: tabs.setdefault(tab, []).append(row))
    return tabs


@pytest.fixture
def folder(monkeypatch):
    """A fake Drive folder: the files in it, and the ids marked as done."""
    state = {"files": [], "done": []}
    monkeypatch.setenv("RECEIPTS_FOLDER_ID", "receipts")
    monkeypatch.setenv("VIDEOS_FOLDER_ID", "videos")
    monkeypatch.setattr(drive, "new_files", lambda folder_id, *types: [
        f for f in state["files"] if f["mimeType"].startswith(types) and f["id"] not in state["done"]])
    monkeypatch.setattr(drive, "download", lambda file_id: f"contents of {file_id}".encode())
    monkeypatch.setattr(drive, "mark_done", state["done"].append)
    return state


def file(file_id, name, mime):
    return {"id": file_id, "name": name, "mimeType": mime, "webViewLink": f"https://drive/{file_id}"}


# Triggers

def test_job_runs_the_automation_and_logs_one_line(capsys):
    triggers.job(hello_job.run)

    assert json.loads(capsys.readouterr().out) == {"message": "Hello, world!"}


def test_job_logs_an_error_line_and_fails_when_the_automation_fails(capsys):
    def broken():
        raise ValueError("the sheet is missing")

    with pytest.raises(ValueError):
        triggers.job(broken)
    assert json.loads(capsys.readouterr().out) == {"severity": "ERROR", "error": "the sheet is missing"}


def test_webhook_checks_the_token_then_runs_the_automation(monkeypatch):
    monkeypatch.setenv("WEBHOOK_TOKEN", "secret")
    client = TestClient(triggers.webhook_app(hello_webhook.run))

    assert client.post("/hook", json={"name": "Owain"}).status_code == 401
    assert client.post("/hook", json={"name": "Owain"}, headers={"X-Token": "wrong"}).status_code == 401
    assert client.post("/hook", json={"name": "Owain"}, headers={"X-Token": "secret"}).json() == {"message": "Hello, Owain!"}
    assert client.post("/hook", headers={"X-Token": "secret"}).json() == {"message": "Hello, world!"}


# 03

def advert(employer, title):
    return job_leads.Job(employer=employer, title=title, town="Cardiff", posted="2026-11-10", link=f"https://redirect/{employer}")


def test_job_leads_adds_only_the_adverts_the_sheet_does_not_have(sheet, monkeypatch):
    sheet["Job leads"] = [["Found", "Employer", "Title"], ["2026-11-10", "Dunbia", "Payroll Assistant"]]
    asked = {}

    def fake_ask(prompt, shape, search):
        asked.update(prompt=prompt, search=search)
        return shape(jobs=[advert("Dunbia", "Payroll Assistant"), advert("BBC", "Finance Manager"),
                           advert("bbc", "finance manager"), advert("Dunbia", "Accountant")])

    monkeypatch.setattr(ai, "ask", fake_ask)
    monkeypatch.setattr(web, "follow", lambda link: link.replace("redirect", "real"))

    result = job_leads.run()

    assert result == {"added": ["BBC: Finance Manager", "Dunbia: Accountant"]}
    assert asked["search"] is True and "Dunbia, Payroll Assistant" in asked["prompt"]  # the model is told what we have
    assert [row[1:] for row in sheet["Job leads"][2:]] == [
        ["BBC", "Finance Manager", "Cardiff", "2026-11-10", "https://real/BBC"],
        ["Dunbia", "Accountant", "Cardiff", "2026-11-10", "https://real/Dunbia"]]


def test_webhook_answers_400_when_the_automation_cannot_use_what_was_sent(monkeypatch, sheet):
    monkeypatch.setenv("WEBHOOK_TOKEN", "secret")
    client = TestClient(triggers.webhook_app(speed_to_lead.run))

    assert client.post("/hook", json={"name": "Sam"}, headers={"X-Token": "secret"}).status_code == 400
    assert sheet == {}


# 04

ENQUIRY = {"name": "Sam Price", "email": "sam@example.com", "company": "Price Engineering", "message": "Two site managers"}


def test_speed_to_lead_saves_the_enquiry_with_a_drafted_reply(sheet, monkeypatch):
    monkeypatch.setattr(ai, "ask", lambda prompt: f"  Hi Sam, thanks. ({'Two site managers' in prompt})  ")
    told = []
    monkeypatch.setattr(web, "notify", lambda text: told.append(text) or True)

    result = speed_to_lead.run(ENQUIRY)

    assert result == {"status": "reply drafted", "team_told": True, "reply": "Hi Sam, thanks. (True)"}
    assert sheet["Enquiries"][0][1:] == ["Sam Price", "sam@example.com", "Price Engineering", "Two site managers",
                                        "Hi Sam, thanks. (True)", "reply drafted"]
    assert "Sam Price" in told[0]


def test_speed_to_lead_never_loses_the_lead_when_the_model_fails(sheet, monkeypatch):
    def broken(prompt):
        raise RuntimeError("model is down")

    monkeypatch.setattr(ai, "ask", broken)
    monkeypatch.setattr(web, "notify", lambda text: False)

    assert speed_to_lead.run(ENQUIRY)["status"] == "needs a reply"
    assert sheet["Enquiries"][0][1:] == ["Sam Price", "sam@example.com", "Price Engineering", "Two site managers",
                                        "", "needs a reply"]


# 05

def test_receipts_adds_a_row_per_receipt_and_never_does_one_twice(sheet, folder, monkeypatch):
    folder["files"] = [file("a", "taxi.pdf", "application/pdf"), file("b", "lunch.jpg", "image/jpeg"),
                       file("c", "notes.txt", "text/plain")]
    seen = []

    def fake_ask(prompt, shape, file):
        seen.append(file)
        return shape(merchant="Dragon Taxis", date="2026-11-10", total=18.5, currency="GBP", category="Travel")

    monkeypatch.setattr(ai, "ask", fake_ask)

    assert receipts.run() == {"saved": ["taxi.pdf", "lunch.jpg"]}
    assert seen == [(b"contents of a", "application/pdf"), (b"contents of b", "image/jpeg")]
    assert sheet["Expenses"][0][1:] == ["Dragon Taxis", "2026-11-10", 18.5, "GBP", "Travel", "https://drive/a"]
    assert folder["done"] == ["a", "b"]
    assert receipts.run() == {"saved": []} and len(sheet["Expenses"]) == 2  # a second run finds nothing new


def test_receipts_saves_the_good_ones_then_fails_the_run_for_the_bad_one(sheet, folder, monkeypatch):
    folder["files"] = [file("bad", "blurry.jpg", "image/jpeg"), file("a", "taxi.pdf", "application/pdf")]

    def fake_ask(prompt, shape, file):
        if file[0] == b"contents of bad":
            raise RuntimeError("cannot read it")
        return shape(merchant="Dragon Taxis", date="2026-11-10", total=18.5, currency="GBP", category="Travel")

    monkeypatch.setattr(ai, "ask", fake_ask)

    with pytest.raises(RuntimeError, match="saved 1, could not read 1: blurry.jpg"):
        receipts.run()
    assert len(sheet["Expenses"]) == 1 and folder["done"] == ["a"]  # the bad file stays for a person


# 06

def test_video_agent_can_only_save_listed_formats_once(sheet, folder, monkeypatch):
    folder["files"] = [file("v1", "talk.mp4", "video/mp4")]
    sheet["Content"] = [["2026-11-01", "other.mp4", "Newsletter", "someone else's draft"]]
    monkeypatch.setattr(ai, "transcribe", lambda recording: f"transcript of {recording.decode()}")
    replies = []

    def fake_agent(instruction, task, tools, max_turns):
        get_transcript, existing_drafts, save_draft = tools
        transcript = get_transcript()
        replies.append(existing_drafts())
        replies.append(save_draft("Reel script", f"reel from {transcript}"))
        replies.append(save_draft("Reel script", "a second copy"))
        replies.append(save_draft("Tweet", "not a listed format"))
        return "Saved a Reel script."

    monkeypatch.setattr(ai, "agent", fake_agent)

    result = video.run()

    assert replies[0] == []  # another video's drafts are not this video's
    assert replies[1] == "Saved." and replies[2].startswith("Not saved") and replies[3].startswith("Refused")
    assert result == {"videos": [{"video": "talk.mp4", "drafts": ["Reel script"], "report": "Saved a Reel script."}]}
    assert sheet["Content"][-1][1:] == ["talk.mp4", "Reel script", "reel from transcript of contents of v1"]
    assert folder["done"] == ["v1"]


def test_video_is_left_for_the_next_run_when_the_agent_fails(sheet, folder, monkeypatch):
    folder["files"] = [file("v1", "talk.mp4", "video/mp4")]

    def failing_agent(instruction, task, tools, max_turns):
        raise RuntimeError("too many turns")

    monkeypatch.setattr(ai, "agent", failing_agent)

    with pytest.raises(RuntimeError):
        video.run()
    assert folder["done"] == []

"""The course examples in examples/ against fake Sheets and a fake model, so the tests need no keys."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

EXAMPLES = Path(__file__).parent.parent / "examples"
sys.path.insert(0, str(EXAMPLES))  # the examples import the toolkit from their own folder

from toolkit import ai, sheets, triggers, web  # noqa: E402


def load(name: str):
    """Import an example by file name: "01-hello_job" can't be imported the usual way."""
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), EXAMPLES / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hello_job, hello_webhook, job_leads = load("01-hello_job"), load("02-hello_webhook"), load("03-job_leads")


@pytest.fixture
def sheet(monkeypatch):
    """A fake sheet: tab name -> rows."""
    tabs = {}
    monkeypatch.setattr(sheets, "read", lambda tab: tabs.get(tab, []))
    monkeypatch.setattr(sheets, "add", lambda tab, row: tabs.setdefault(tab, []).append(row))
    return tabs


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

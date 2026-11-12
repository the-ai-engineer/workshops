"""Fakes for the outside world, so the tests run in seconds with no Google account."""
import importlib.util
from pathlib import Path

import pytest

from toolkit import ai, mail, sheets, slack

AUTOMATIONS = Path(__file__).parents[1] / "automations"


def load(name: str):
    """Import an automation by file name. Files that start with a number can't be imported the usual way."""
    spec = importlib.util.spec_from_file_location(name, AUTOMATIONS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class World:
    """Everything the automations touched: sheet rows, Slack messages and emails."""

    def __init__(self):
        self.tabs: dict[str, list[list]] = {}
        self.slack: list[str] = []
        self.emails: list[dict] = []
        self.answer = None  # what the fake model says, or an exception it raises


@pytest.fixture
def world(monkeypatch) -> World:
    w = World()
    monkeypatch.setenv("SHADOW", "false")
    monkeypatch.setattr(sheets, "read", lambda tab: w.tabs.get(tab, []))
    monkeypatch.setattr(sheets, "add", lambda tab, row: w.tabs.setdefault(tab, []).append(row))
    monkeypatch.setattr(slack, "post", lambda text: w.slack.append(text) or True)

    def send(to, subject, text, key):
        w.emails.append({"to": to, "subject": subject, "text": text, "key": key})
        return True

    def ask(prompt, shape=None, search=False):
        if isinstance(w.answer, Exception):
            raise w.answer
        return w.answer(prompt) if callable(w.answer) else w.answer

    monkeypatch.setattr(mail, "send", send)
    monkeypatch.setattr(ai, "ask", ask)
    return w

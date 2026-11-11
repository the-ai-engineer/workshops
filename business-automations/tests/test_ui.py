"""The control panel in ui/: it serves the page and only runs what is on its list."""
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent / "ui"))

import app  # noqa: E402

client = TestClient(app.app)


def test_serves_the_page_and_its_links(monkeypatch):
    assert "Automations" in client.get("/").text
    assert set(client.get("/config").json()) == {"project", "region", "sheet", "receipts", "videos"}


def test_only_runs_the_jobs_and_webhooks_on_its_list():
    assert client.post("/run/job/anything-else").status_code == 404
    assert client.post("/run/webhook/anything-else", json={}).status_code == 404
    assert client.get("/logs/not-an-example").status_code == 404

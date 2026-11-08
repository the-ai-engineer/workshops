"""Each automation against fake Google, Claude and email, so the tests need no keys."""
import pytest
from fastapi.testclient import TestClient

from automations import client_folder, invoice_inbox, meeting_reminders


@pytest.fixture(autouse=True)
def env(monkeypatch):
    for key, value in {
        "AUTOMATION_TOKEN": "secret", "INBOX_FOLDER_ID": "inbox", "PROCESSED_FOLDER_ID": "done",
        "INVOICES_SHEET_ID": "invoices", "CLIENTS_FOLDER_ID": "clients", "CLIENTS_SHEET_ID": "crm",
        "CALENDAR_ID": "cal", "OWN_DOMAIN": "us.com", "TIMEZONE": "Europe/London",
    }.items():
        monkeypatch.setenv(key, value)


class FakeGoogle:
    def __init__(self, files=(), folders=(), events=()):
        self.files, self.folders, self.events = list(files), dict(folders), list(events)
        self.rows, self.moved, self.created = [], [], []

    def list_files(self, folder_id):
        return list(self.files)

    def download(self, file_id):
        if file_id == "broken":
            raise ValueError("can't read")
        return b"%PDF"

    def move(self, file_id, from_folder, to_folder):
        self.moved.append((file_id, from_folder, to_folder))

    def append_row(self, sheet_id, tab, row):
        self.rows.append((sheet_id, tab, row))

    def find_folder(self, parent_id, name):
        return self.folders.get(name)

    def create_folder(self, parent_id, name):
        self.created.append((parent_id, name))
        return {"id": f"id-{name}", "webViewLink": f"https://drive/{name}"}

    def events_between(self, calendar_id, start, end):
        return self.events


def pdf(file_id, name):
    return {"id": file_id, "name": name, "mimeType": "application/pdf", "webViewLink": f"https://drive/{file_id}"}


def test_invoice_inbox_adds_a_row_and_moves_each_pdf(monkeypatch):
    fake = FakeGoogle(files=[
        pdf("a", "acme.pdf"),
        {"id": "b", "name": "notes.txt", "mimeType": "text/plain", "webViewLink": ""},
        pdf("broken", "bad.pdf"),
    ])
    monkeypatch.setattr(invoice_inbox, "google", fake)
    monkeypatch.setattr(invoice_inbox, "extract", lambda prompt, schema, pdf: invoice_inbox.Invoice(
        supplier="Acme", invoice_number="INV-1", invoice_date="2026-11-01", due_date="2026-12-01",
        currency="GBP", total=120.0))

    result = invoice_inbox.run()

    assert [r["supplier"] for r in result["processed"]] == ["Acme"]
    assert result["failed"] == [{"file": "bad.pdf", "error": "can't read"}]
    assert fake.rows[0][:2] == ("invoices", "Invoices")
    assert fake.rows[0][2][1:] == ["Acme", "INV-1", "2026-11-01", "2026-12-01", "GBP", 120.0, "https://drive/a"]
    assert fake.moved == [("a", "inbox", "done")]  # the broken file stays in Inbox for the next run


def test_client_folder_creates_folder_subfolders_and_row(monkeypatch):
    fake = FakeGoogle()
    monkeypatch.setattr(client_folder, "google", fake)

    result = client_folder.run({"name": "Acme Ltd", "email": "jo@acme.com"})

    assert result == {"created": True, "folder": "https://drive/Acme Ltd"}
    assert fake.created[0] == ("clients", "Acme Ltd")
    assert [name for _, name in fake.created[1:]] == client_folder.SUBFOLDERS
    assert fake.rows[0][2][1:] == ["Acme Ltd", "jo@acme.com", "https://drive/Acme Ltd"]


def test_client_folder_does_nothing_when_folder_exists(monkeypatch):
    fake = FakeGoogle(folders={"Acme Ltd": {"id": "x", "webViewLink": "https://drive/x"}})
    monkeypatch.setattr(client_folder, "google", fake)

    assert client_folder.run({"name": "Acme Ltd", "email": "jo@acme.com"}) == {"created": False, "folder": "https://drive/x"}
    assert fake.created == [] and fake.rows == []


def test_meeting_reminders_emails_outside_guests_only(monkeypatch):
    fake = FakeGoogle(events=[
        {"summary": "Kick-off", "start": {"dateTime": "2026-11-12T10:00:00Z"}, "hangoutLink": "https://meet/x",
         "attendees": [{"email": "me@us.com"}, {"email": "jo@acme.com"},
                       {"email": "no@acme.com", "responseStatus": "declined"},
                       {"email": "room@resource.calendar.google.com", "resource": True}]},
        {"summary": "Holiday", "start": {"date": "2026-11-12"}, "attendees": [{"email": "jo@acme.com"}]},
    ])
    sent = []
    monkeypatch.setattr(meeting_reminders, "google", fake)
    monkeypatch.setattr(meeting_reminders.mail, "send", lambda to, subject, body: sent.append((to, subject, body)))

    result = meeting_reminders.run({"date": "2026-11-12"})

    assert [s["to"] for s in result["sent"]] == ["jo@acme.com"]
    assert sent[0][1] == "Reminder: Kick-off tomorrow at 10:00"
    assert "https://meet/x" in sent[0][2]


def test_service_needs_the_token(monkeypatch):
    import main

    monkeypatch.setitem(main.AUTOMATIONS, "invoice_inbox", lambda payload: {"ok": True})
    client = TestClient(main.app)

    assert client.post("/run/invoice_inbox").status_code == 401
    assert client.post("/run/nope", headers={"X-Token": "secret"}).status_code == 404
    assert client.post("/run/invoice_inbox", headers={"X-Token": "secret"}).json() == {"ok": True}

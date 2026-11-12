import time

import pytest
from fastapi.testclient import TestClient

from toolkit import retry, shadow, triggers

SECRET = "test-secret"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("WEBHOOK_TOKEN", "right-token")
    monkeypatch.setenv("WEBHOOK_SECRET", SECRET)
    ran = []

    def run(payload):
        ran.append(payload)
        if "name" not in payload:
            raise KeyError("name")
        return {"hello": payload["name"]}

    return ran, TestClient(triggers.webhook_app(run)), TestClient(triggers.webhook_app(run, check="signature"))


def test_job_prints_one_line_and_fails_loudly(capsys):
    triggers.job(lambda: {"ok": True})
    assert '"status": "ok"' in capsys.readouterr().out
    with pytest.raises(RuntimeError):
        triggers.job(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert '"severity": "ERROR"' in capsys.readouterr().out


def test_wrong_token_is_rejected_before_run(client):
    ran, token_hook, _ = client
    assert token_hook.post("/hook", json={"name": "Sam"}, headers={"X-Token": "wrong"}).status_code == 401
    assert ran == []
    assert token_hook.post("/hook", json={"name": "Sam"}, headers={"X-Token": "right-token"}).json() == {"hello": "Sam"}


def test_bad_request_is_a_400(client):
    _, token_hook, _ = client
    assert token_hook.post("/hook", json={}, headers={"X-Token": "right-token"}).status_code == 400


def test_signed_request_is_accepted(client):
    ran, _, signed_hook = client
    body = b'{"name": "Sam"}'
    response = signed_hook.post("/hook", content=body, headers={"X-Signature": triggers.sign(body, SECRET)})
    assert response.status_code == 200 and ran == [{"name": "Sam"}]


def test_changed_body_is_rejected(client):
    ran, _, signed_hook = client
    signature = triggers.sign(b'{"name": "Sam"}', SECRET)
    response = signed_hook.post("/hook", content=b'{"name": "Eve"}', headers={"X-Signature": signature})
    assert response.status_code == 401 and ran == []


def test_old_request_is_rejected(client):
    ran, _, signed_hook = client
    body = b'{"name": "Sam"}'
    old = triggers.sign(body, SECRET, timestamp=int(time.time()) - 3600)
    assert signed_hook.post("/hook", content=body, headers={"X-Signature": old}).status_code == 401
    assert signed_hook.post("/hook", content=body, headers={"X-Signature": "nonsense"}).status_code == 401
    assert ran == []


def test_shadow_mode_is_on_unless_switched_off(monkeypatch):
    monkeypatch.delenv("SHADOW", raising=False)
    assert shadow.on() and shadow.skip("send", "hi")
    monkeypatch.setenv("SHADOW", "false")
    assert not shadow.skip("send", "hi")


def test_retry_tries_temporary_failures_again_and_gives_up_on_others():
    import httpx

    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise httpx.ConnectError("dropped")
        return "ok"

    assert retry.call(flaky, wait=0) == "ok" and len(calls) == 3

    def bad():
        calls.append(1)
        raise ValueError("bad request")

    calls.clear()
    with pytest.raises(ValueError):
        retry.call(bad, wait=0)
    assert len(calls) == 1

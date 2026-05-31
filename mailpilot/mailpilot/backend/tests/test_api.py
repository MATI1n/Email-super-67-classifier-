"""Смоук-тесты REST API (FastAPI TestClient)."""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["emails_loaded"] >= 100
    assert body["ai_mode"] in ("mock", "deepseek")


def test_folders(client):
    d = client.get("/api/folders").json()
    assert d["folders"]["inbox"] >= 100
    assert len(d["categories"]) == 7
    assert len(d["tags"]) == 6


def test_list_and_filter(client):
    full = client.get("/api/emails", params={"folder": "inbox"}).json()
    assert full["total"] >= 100
    payment = client.get("/api/emails", params={"folder": "inbox", "tag": "payment"}).json()
    assert 0 < payment["total"] < full["total"]


def test_unknown_tag_rejected(client):
    r = client.get("/api/emails", params={"folder": "inbox", "tag": "nope"})
    assert r.status_code == 400


def test_email_detail_marks_read(client):
    d = client.get("/api/emails/mail_0009").json()
    assert d["unread"] is False
    assert d["ticket_id"] == "TIC-0009"
    assert "body" in d


def test_search_endpoint(client):
    d = client.get("/api/search", params={"q": "zoom не запускается"}).json()
    assert d["count"] > 0
    assert "channels" in d["results"][0]
    assert "match_snippet" in d["results"][0]


def test_summarize_endpoint(client):
    d = client.post("/api/emails/mail_0009/summarize", json={"scope": "ticket"}).json()
    assert d["summary"]
    assert d["scope"] == "ticket"
    assert isinstance(d["highlights"], list)


def test_action_star_and_archive(client):
    assert client.post("/api/emails/mail_0050/action", json={"action": "star"}).json()["starred"] is True
    assert client.post("/api/emails/mail_0050/action", json={"action": "archive"}).json()["archived"] is True
    # вернуть исходное состояние
    client.post("/api/emails/mail_0050/action", json={"action": "unarchive"})
    client.post("/api/emails/mail_0050/action", json={"action": "unstar"})


def test_action_invalid(client):
    r = client.post("/api/emails/mail_0001/action", json={"action": "explode"})
    assert r.status_code == 400


def test_404_for_missing_email(client):
    assert client.get("/api/emails/does_not_exist").status_code == 404

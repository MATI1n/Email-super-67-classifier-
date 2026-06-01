"""Тесты хранилища: загрузка датасета, edge-cases, папки, действия."""
import pytest

from app.config import settings
from app.store import MailStore


@pytest.fixture(scope="module")
def store():
    s = MailStore(settings.data_dir)
    s.load()
    return s


def test_dataset_loaded(store):
    assert len(store.all()) >= 100  # ~109 писем в наборе


def test_edge_cases_go_to_errors(store):
    # Бинарный файл и картинка не должны ронять приложение → категория errors.
    assert store.get("mail_0104").category == "errors"   # .bin
    assert store.get("mail_0109").category == "errors"   # .jpeg
    assert store.get("mail_0105").category == "errors"   # повреждённый .json
    # Письмо с заголовками без расширения — наоборот, должно разобраться.
    assert store.get("mail_0106") is not None
    assert store.get("mail_0106").category != "errors"


def test_error_email_has_reason(store):
    e = store.get("mail_0104")
    assert e.error_reason is not None
    assert e.priority == "low"


def test_ticket_id_one_per_email(store):
    e = store.get("mail_0001")
    assert e.ticket_id == "TIC-0001"


def test_attachments_extracted(store):
    # mail_0013: "Во вложении: screenshot.png"
    e = store.get("mail_0013")
    assert any(a.lower().endswith(".png") for a in e.attachments)


def test_folder_filtering_and_actions(store):
    inbox_before = len(store.query(folder="inbox"))

    store.toggle_star("mail_0002")
    assert store.get("mail_0002").starred is True
    assert any(e.id == "mail_0002" for e in store.query(folder="starred"))

    store.archive("mail_0002", True)
    assert all(e.id != "mail_0002" for e in store.query(folder="inbox"))
    assert any(e.id == "mail_0002" for e in store.query(folder="archive"))
    assert len(store.query(folder="inbox")) == inbox_before - 1

    store.archive("mail_0002", False)  # вернуть
    store.toggle_star("mail_0002")


def test_counts_structure(store):
    c = store.counts()
    assert "folders" in c and "categories" in c and "tags" in c
    assert c["total"] == len(store.all())
    assert all("count" in t for t in c["tags"])


def test_mark_read(store):
    store.mark_read("mail_0001", True)
    assert store.get("mail_0001").unread is False

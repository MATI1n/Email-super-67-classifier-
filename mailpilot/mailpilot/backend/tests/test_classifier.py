"""Тесты классификации: базовые категории + теги по типу проблемы."""
import pytest

from app.classifier import classify, classify_category, detect_tags, derive_priority
from app.letter import Letter


def L(subject="", body="", sender="a@b.ru"):
    return Letter(f"From: {sender}\nSubject: {subject}\n\n{body}")


@pytest.mark.parametrize("subject,body,sender,expected", [
    ("Выгодная скидка", "Казино и выигрыш", "promo@x.ru", "spam"),
    ("Healthcheck", "ALERT: database cluster", "grafana@int", "alerts"),
    ("Плановый отчёт", "Автоматическое уведомление от системы", "noreply@jira", "alerts"),
    ("URGENT", "критичный инцидент, работа остановлена", "u@c.ru", "urgent"),
    ("Корпоративный дайджест — выпуск #11", "новости", "n@c.ru", "newsletters"),
    ("Заявление на отпуск", "прошу согласовать отпуск", "hr@c.ru", "hr_documents"),
    ("Вопрос по работе", "не могу разобраться", "user@c.ru", "support"),  # fallback
])
def test_base_categories(subject, body, sender, expected):
    assert classify_category(L(subject, body, sender)) == expected


def test_tags_multilabel():
    tags = detect_tags(L("Не могу войти", "ошибка при входе, не работает логин и пароль"))
    assert "access" in tags
    assert "bug" in tags  # «не работает» + «ошибка»


def test_tags_payment_and_hardware():
    assert "payment" in detect_tags(L("Счёт", "просьба передать в бухгалтерию для оплаты"))
    assert "hardware" in detect_tags(L("Гарнитура", "сканер не включается, нужен ремонт"))


def test_tags_may_be_empty():
    assert detect_tags(L("Привет", "просто хотел уточнить расписание")) == []


def test_priority_high_for_incident():
    c = classify(L("URGENT", "критичный инцидент, затронуты 15 сотрудников"))
    assert c.priority == "high"
    assert "incident" in c.tags


def test_priority_low_for_spam():
    assert derive_priority("spam", []) == "low"
    assert derive_priority("support", ["bug"]) == "normal"

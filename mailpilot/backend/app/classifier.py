"""Классификация писем.

Два уровня:

1. БАЗОВЫЙ (как в исходном репозитории) — ``classify_category``: правила по
   ключевым словам раскладывают письмо в одну смысловую категорию-папку.
   Категории и ключевые слова сохранены из базового классификатора.

2. ПРОДВИНУТЫЙ — ``detect_tags``: мульти-лейбл теги по *типу проблемы*
   (баги, оплата, доступ/регистрация, оборудование, кадры, инцидент).
   Одно письмо может получить несколько тегов. Реализовано как отдельный
   слой, чтобы при наличии ML-модели его можно было заменить, не трогая
   остальной код.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .letter import Letter

# --------------------------------------------------------------------------- #
# Уровень 1. Базовые категории-папки (из исходного репозитория).
# --------------------------------------------------------------------------- #
CATEGORIES = [
    "urgent",       # Важные / срочные инциденты
    "alerts",       # Автоуведомления систем мониторинга
    "spam",         # Спам и реклама
    "hr_documents", # Кадры, отпуска, согласование документов
    "newsletters",  # Корпоративные дайджесты и рассылки
    "support",      # Обычные запросы в поддержку (fallback, в репо — "unknown")
    "errors",       # Нечитаемые / повреждённые / неизвестный формат
]

_SPAM_KW = ["casino", "win", "discount", "скидк", "выигрыш", "реклама", "казино",
            "будет заблокирован", "акция", "розыгрыш", "приз"]
_ALERT_SENDER_KW = ["alert", "grafana", "zabbix", "prometheus", "noreply",
                    "no-reply", "daemon", "monitoring", "jira.internal"]
_ALERT_BODY_KW = ["healthcheck", "автоматическое уведомление", "сгенерировано автоматически",
                  "cpu usage", "database cluster", "метрика", "alert:"]
_URGENT_KW = ["urgent", "срочно", "критичн", "падает", "ошибка 500", "error 500",
              "инцидент", "недоступен", "работа остановлена", "немедленно"]
_NEWS_KW = ["дайджест", "newsletter", "рассылка", "новост", "выпуск #", "digest"]
_HR_KW = ["отпуск", "больничный", "инструкция на согласование", "согласование",
          "договор на согласование", "заявление", "кадров"]


def classify_category(letter: Letter) -> str:
    """Базовая классификация письма в одну категорию (правила репозитория)."""
    subject = (letter.subject or "").lower()
    text = (letter.text or "").lower()
    sender = (letter.from_email or "").lower()
    blob = f"{subject}\n{text}"

    if any(k in blob for k in _SPAM_KW):
        return "spam"
    if any(k in sender for k in _ALERT_SENDER_KW) or any(k in blob for k in _ALERT_BODY_KW):
        return "alerts"
    if any(k in blob for k in _URGENT_KW):
        return "urgent"
    if any(k in blob for k in _NEWS_KW):
        return "newsletters"
    if any(k in blob for k in _HR_KW):
        return "hr_documents"
    return "support"


# --------------------------------------------------------------------------- #
# Уровень 2. Теги по типу проблемы (мульти-лейбл).
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class TagDef:
    id: str
    label: str       # человекочитаемое имя для UI
    color: str       # цвет чипа в интерфейсе
    keywords: tuple


TAG_DEFS: List[TagDef] = [
    TagDef("bug", "Баги системы", "#e5484d", (
        "не работает", "не работают", "ошибка", "ошибк", "зависает", "зависл",
        "вылетает", "падает", "упал", "не открыва", "не запуска", "не отвеча",
        "глючит", "сломал", "баг", "крашит", "не загружа", "перестал",
        "недоступен", "не определяется", "error", "500", "не реагирует",
    )),
    TagDef("access", "Доступ и вход", "#4263eb", (
        "не могу войти", "не получается войти", "вход", "логин", "пароль",
        "доступ", "права доступа", "учётная запись", "учетная запись", "аккаунт",
        "регистрац", "заблокирован", "выдать доступ", "нет доступа", "gitlab",
        "vpn", "авториз", "не пускает",
    )),
    TagDef("payment", "Оплата и счета", "#0ca678", (
        "оплат", "платёж", "платеж", "счёт", "счет", "счёта", "акт ", "акта",
        "договор", "бухгалтер", "invoice", "billing", "закрывающие", "финанс",
        "возврат средств", "транзакц",
    )),
    TagDef("hardware", "Оборудование", "#f08c00", (
        "оборудован", "гарнитур", "сканер", "принтер", "мышь", "клавиатур",
        "монитор", "ноутбук", "устройств", "не включается", "ремонт",
        "замена", "неисправност", "железо",
    )),
    TagDef("hr", "Кадры и доступы", "#ae3ec9", (
        "отпуск", "больничный", "новый сотрудник", "нового сотрудника",
        "рабочее место", "приём на работу", "прием на работу", "увольнен",
        "кадров", "онбординг",
    )),
    TagDef("incident", "Срочный инцидент", "#d6336c", (
        "срочно", "urgent", "критичн", "инцидент", "немедленно", "горит",
        "работа остановлена", "затронуты", "массов",
    )),
]

TAG_BY_ID = {t.id: t for t in TAG_DEFS}


def detect_tags(letter: Letter) -> List[str]:
    """Вернуть список id тегов по типу проблемы (может быть несколько)."""
    blob = f"{(letter.subject or '')}\n{(letter.text or '')}".lower()
    tags = [t.id for t in TAG_DEFS if any(k in blob for k in t.keywords)]
    return tags


def derive_priority(category: str, tags: List[str]) -> str:
    """Приоритет письма для сортировки и UI: high / normal / low."""
    if category == "urgent" or "incident" in tags:
        return "high"
    if category in ("spam", "newsletters", "alerts"):
        return "low"
    return "normal"


# --------------------------------------------------------------------------- #
# Результат классификации одного письма.
# --------------------------------------------------------------------------- #
@dataclass
class Classification:
    category: str
    tags: List[str]
    priority: str
    error_reason: Optional[str] = None


def classify(letter: Letter) -> Classification:
    category = classify_category(letter)
    tags = detect_tags(letter)
    priority = derive_priority(category, tags)
    return Classification(category=category, tags=tags, priority=priority)

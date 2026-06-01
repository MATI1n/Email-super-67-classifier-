"""Хранилище писем (in-memory).

Загружает письма из файловой системы, классифицирует их, формирует папки,
теги и заявки и предоставляет операции почтового клиента (чтение, фильтры,
пометки, архив, удаление). По условию задачи: 1 письмо = 1 заявка.

Робастность к «грязным» данным (намеренная особенность датасета):
  * бинарные/нечитаемые файлы (.bin, .jpeg) → категория ``errors``;
  * повреждённый JSON → ``errors`` с пояснением;
  * письма без части заголовков всё равно обрабатываются.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from .classifier import TAG_DEFS, classify
from .letter import Letter

# Системные папки почтового клиента.
SYSTEM_FOLDERS = ["inbox", "sent", "starred", "archive", "trash", "drafts"]

# Человекочитаемые имена категорий (для «умных» папок в сайдбаре).
CATEGORY_LABELS = {
    "urgent": "Срочные",
    "alerts": "Уведомления",
    "spam": "Спам",
    "hr_documents": "Кадры",
    "newsletters": "Рассылки",
    "support": "Поддержка",
    "errors": "Ошибки",
}

_ATTACH_RE = re.compile(
    r"\b([\w\-]+\.(?:png|jpe?g|pdf|docx?|xlsx?|pptx?|zip|rar|fig|csv|txt|json|log))\b",
    re.IGNORECASE,
)

# Якорь времени для синтетических дат «получения» (датасет — демо-ящик).
_BASE_TIME = datetime(2026, 5, 31, 9, 30)


@dataclass
class Email:
    id: str
    filename: str
    from_name: str
    from_email: str
    to: Optional[str]
    subject: str
    body: str
    received_at: datetime
    header_date: Optional[str]
    category: str
    tags: List[str]
    priority: str
    attachments: List[str] = field(default_factory=list)
    error_reason: Optional[str] = None
    # Состояние в ящике
    folder: str = "inbox"
    unread: bool = True
    starred: bool = False
    archived: bool = False
    deleted: bool = False

    @property
    def ticket_id(self) -> str:
        # 1 письмо = 1 заявка.
        return f"TIC-{self.id.split('_')[-1]}"

    @property
    def snippet(self) -> str:
        text = " ".join(self.body.split())
        return (text[:140] + "…") if len(text) > 140 else text

    def to_list_item(self) -> dict:
        return {
            "id": self.id,
            "ticket_id": self.ticket_id,
            "from_name": self.from_name,
            "from_email": self.from_email,
            "subject": self.subject or "(без темы)",
            "snippet": self.snippet,
            "received_at": self.received_at.isoformat(),
            "category": self.category,
            "category_label": CATEGORY_LABELS.get(self.category, self.category),
            "tags": self.tags,
            "priority": self.priority,
            "has_attachments": bool(self.attachments),
            "attachments": self.attachments,
            "unread": self.unread,
            "starred": self.starred,
            "archived": self.archived,
            "deleted": self.deleted,
        }

    def to_detail(self) -> dict:
        d = self.to_list_item()
        d.update({
            "to": self.to,
            "body": self.body,
            "header_date": self.header_date,
            "error_reason": self.error_reason,
            "filename": self.filename,
        })
        return d


class MailStore:
    """Главное хранилище писем приложения."""

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.emails: Dict[str, Email] = {}
        self._order: List[str] = []

    # ------------------------------------------------------------------ #
    def load(self) -> None:
        self.emails.clear()
        self._order.clear()
        if not self.data_dir.exists():
            raise FileNotFoundError(f"Каталог с письмами не найден: {self.data_dir}")

        files = sorted(self.data_dir.iterdir(), key=lambda p: p.name)
        for idx, path in enumerate(f for f in files if f.is_file() and f.name != ".DS_Store"):
            email = self._load_one(path, idx)
            self.emails[email.id] = email
            self._order.append(email.id)

        # Сортировка по дате получения (новые сверху).
        self._order.sort(key=lambda i: self.emails[i].received_at, reverse=True)

    def _load_one(self, path: Path, idx: int) -> Email:
        mail_id = path.stem if path.suffix else path.name
        received_at = _BASE_TIME - timedelta(hours=idx * 3.3)

        raw_bytes = path.read_bytes()
        # 1) Попытка декодировать как текст.
        try:
            raw = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return self._error_email(
                mail_id, path.name, received_at,
                "Не удалось прочитать файл: бинарные/нетекстовые данные.",
            )

        stripped = raw.strip()
        # 2) JSON-формат письма.
        if path.suffix.lower() == ".json" or stripped.startswith("{"):
            return self._load_json(mail_id, path.name, received_at, raw)

        # 3) Обычное письмо с заголовками.
        letter = Letter(raw)
        if not letter.is_meaningful:
            return self._error_email(
                mail_id, path.name, received_at,
                "Письмо пустое или не содержит распознаваемых данных.",
            )
        return self._email_from_letter(mail_id, path.name, received_at, letter)

    def _load_json(self, mail_id, filename, received_at, raw) -> Email:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return self._error_email(
                mail_id, filename, received_at,
                "Повреждённый JSON: письмо не удалось разобрать.",
            )
        pseudo = "\n".join([
            f"From: {data.get('from', '')}",
            f"Subject: {data.get('subject', '')}",
            "",
            str(data.get("body", "")),
        ])
        letter = Letter(pseudo)
        if not letter.is_meaningful:
            return self._error_email(
                mail_id, filename, received_at,
                "JSON без осмысленного содержимого письма.",
            )
        return self._email_from_letter(mail_id, filename, received_at, letter)

    def _email_from_letter(self, mail_id, filename, received_at, letter: Letter) -> Email:
        cls = classify(letter)
        attachments = self._extract_attachments(letter)
        return Email(
            id=mail_id,
            filename=filename,
            from_name=letter.display_name(),
            from_email=letter.from_email or "unknown@unknown",
            to=letter.to,
            subject=letter.subject or "",
            body=letter.text,
            received_at=received_at,
            header_date=letter.date.isoformat() if letter.date else None,
            category=cls.category,
            tags=cls.tags,
            priority=cls.priority,
            attachments=attachments,
            folder="inbox",
        )

    @staticmethod
    def _extract_attachments(letter: Letter) -> List[str]:
        found = _ATTACH_RE.findall(letter.text or "")
        # Уникализируем, сохраняя порядок.
        seen, result = set(), []
        for name in found:
            low = name.lower()
            if low not in seen:
                seen.add(low)
                result.append(name)
        return result

    @staticmethod
    def _error_email(mail_id, filename, received_at, reason) -> Email:
        return Email(
            id=mail_id,
            filename=filename,
            from_name="Система",
            from_email="system@mailpilot",
            to=None,
            subject=f"⚠ Необработанное письмо: {filename}",
            body=reason,
            received_at=received_at,
            header_date=None,
            category="errors",
            tags=[],
            priority="low",
            error_reason=reason,
            folder="inbox",
            unread=False,
        )

    # ------------------------------------------------------------------ #
    # Запросы
    # ------------------------------------------------------------------ #
    def get(self, mail_id: str) -> Optional[Email]:
        return self.emails.get(mail_id)

    def all(self) -> List[Email]:
        return [self.emails[i] for i in self._order]

    def query(
        self,
        folder: Optional[str] = None,
        category: Optional[str] = None,
        tag: Optional[str] = None,
        unread_only: bool = False,
        starred_only: bool = False,
    ) -> List[Email]:
        result = []
        for email in self.all():
            if not self._in_folder(email, folder):
                continue
            if category and email.category != category:
                continue
            if tag and tag not in email.tags:
                continue
            if unread_only and not email.unread:
                continue
            if starred_only and not email.starred:
                continue
            result.append(email)
        return result

    @staticmethod
    def _in_folder(email: Email, folder: Optional[str]) -> bool:
        if folder in (None, "inbox"):
            return not email.archived and not email.deleted
        if folder == "starred":
            return email.starred and not email.deleted
        if folder == "archive":
            return email.archived and not email.deleted
        if folder == "trash":
            return email.deleted
        if folder == "sent":
            return email.folder == "sent" and not email.deleted
        if folder == "drafts":
            return email.folder == "drafts" and not email.deleted
        return True

    # ------------------------------------------------------------------ #
    # Счётчики для сайдбара
    # ------------------------------------------------------------------ #
    def counts(self) -> dict:
        active = [e for e in self.all() if not e.deleted]
        folder_counts = {f: len(self.query(folder=f)) for f in SYSTEM_FOLDERS}
        folder_counts["inbox_unread"] = sum(
            1 for e in self.query(folder="inbox") if e.unread
        )

        category_counts = []
        for cat, label in CATEGORY_LABELS.items():
            n = sum(1 for e in active if e.category == cat and not e.archived)
            category_counts.append({"id": cat, "label": label, "count": n})

        tag_counts = []
        for t in TAG_DEFS:
            n = sum(1 for e in active if t.id in e.tags and not e.archived)
            tag_counts.append({"id": t.id, "label": t.label, "color": t.color, "count": n})

        return {
            "folders": folder_counts,
            "categories": category_counts,
            "tags": tag_counts,
            "total": len(self.all()),
        }

    # ------------------------------------------------------------------ #
    # Изменения состояния
    # ------------------------------------------------------------------ #
    def mark_read(self, mail_id: str, value: bool = True) -> Optional[Email]:
        e = self.get(mail_id)
        if e:
            e.unread = not value
        return e

    def toggle_star(self, mail_id: str) -> Optional[Email]:
        e = self.get(mail_id)
        if e:
            e.starred = not e.starred
        return e

    def archive(self, mail_id: str, value: bool = True) -> Optional[Email]:
        e = self.get(mail_id)
        if e:
            e.archived = value
        return e

    def delete(self, mail_id: str, value: bool = True) -> Optional[Email]:
        e = self.get(mail_id)
        if e:
            e.deleted = value
        return e

    def set_tags(self, mail_id: str, tags: List[str]) -> Optional[Email]:
        e = self.get(mail_id)
        if e:
            e.tags = tags
        return e

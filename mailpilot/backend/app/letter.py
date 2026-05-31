"""Парсер письма.

Развитие класса ``Letter`` из базового репозитория. Извлекает заголовки
(From / От кого, To / Кому, Subject / Тема, Date / Дата) на русском и
английском, отделяет тело письма и аккуратно обрабатывает частичные или
«грязные» письма (часть датасета намеренно содержит шум).
"""
from __future__ import annotations

import re
from email.utils import parseaddr
from typing import List, Optional

import dateparser

# Один заголовок = одна строка вида "Ключ: значение".
_HEADER_RE = re.compile(
    r"^\s*(?P<key>From|От кого|Ot kogo|To|Кому|Komu|Subject|Тема|Tema|Date|Дата|Data)"
    r"\s*[:\-]\s*(?P<value>.*)$",
    re.IGNORECASE,
)

_KEY_ALIASES = {
    "from": "from", "от кого": "from", "ot kogo": "from",
    "to": "to", "кому": "to", "komu": "to",
    "subject": "subject", "тема": "subject", "tema": "subject",
    "date": "date", "дата": "date", "data": "date",
}


class Letter:
    """Разобранное письмо: отправитель, получатель, тема, дата, текст."""

    def __init__(self, raw_text: str):
        self.raw_text: str = raw_text or ""

        self._from_name: Optional[str] = None
        self._from_email: Optional[str] = None
        self._to: Optional[str] = None
        self._subject: Optional[str] = None
        self._date = None
        self._text: str = ""

        self._parse()

    # ------------------------------------------------------------------ #
    def _parse(self) -> None:
        lines = self.raw_text.splitlines()
        body_lines: List[str] = []
        header_zone = True  # заголовки идут блоком в начале письма

        for line in lines:
            match = _HEADER_RE.match(line) if header_zone else None

            if not match:
                # Пустая строка внутри шапки — граница «шапка/тело».
                if header_zone and line.strip() == "" and self._has_any_header():
                    header_zone = False
                if line.strip() or body_lines:
                    body_lines.append(line)
                continue

            key = _KEY_ALIASES.get(match.group("key").lower(), "")
            value = match.group("value").strip()

            if key == "from" and not self._from_email:
                name, email = parseaddr(value)
                self._from_name = name or None
                self._from_email = email or value or None
            elif key == "to" and not self._to:
                self._to = value or None
            elif key == "subject" and not self._subject:
                self._subject = value or None
            elif key == "date" and not self._date:
                self._date = dateparser.parse(value, settings={"DATE_ORDER": "DMY"})
            else:
                body_lines.append(line)

        self._text = "\n".join(body_lines).strip()

        # Запасной отправитель: первый e-mail из текста письма.
        if not self._from_email:
            found = re.search(r"[\w.\-+]+@[\w.\-]+\.\w+", self.raw_text)
            if found:
                self._from_email = found.group(0)

    def _has_any_header(self) -> bool:
        return any([self._from_email, self._to, self._subject, self._date])

    # ------------------------------------------------------------------ #
    @property
    def from_name(self) -> Optional[str]:
        return self._from_name

    @property
    def from_email(self) -> Optional[str]:
        return self._from_email

    @property
    def to(self) -> Optional[str]:
        return self._to

    @property
    def subject(self) -> Optional[str]:
        return self._subject

    @property
    def date(self):
        return self._date

    @property
    def text(self) -> str:
        return self._text

    @property
    def is_meaningful(self) -> bool:
        """Есть ли в письме минимально осмысленные данные.

        В отличие от базовой версии не требуем наличия *всех* заголовков:
        реальные письма часто приходят без даты или получателя. Достаточно
        отправителя или темы и непустого тела.
        """
        has_meta = bool(self._from_email or self._subject)
        has_body = bool(self._text.strip())
        return has_meta and has_body

    def display_name(self) -> str:
        if self._from_name:
            return self._from_name
        if self._from_email:
            return self._from_email.split("@")[0]
        return "Неизвестный отправитель"

    def __repr__(self) -> str:
        return (
            f"Letter(from={self._from_email!r}, subject={self._subject!r}, "
            f"date={self._date!r}, body_len={len(self._text)})"
        )

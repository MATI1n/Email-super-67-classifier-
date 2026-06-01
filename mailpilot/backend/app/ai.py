"""AI-суммаризатор писем и заявок.

Класс `Summarizer` формирует структурированную сводку по письму:
- Через OpenRouter (если настроен `OPENROUTER_API_KEY_2`).
- Через DeepSeek (если настроен `DEEPSEEK_API_KEY`).
- С помощью встроенного эвристического суммаризатора в качестве локального mock-режима.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import re
from typing import Any, Dict, List

import httpx
from openai import OpenAI

from .classifier import TAG_BY_ID
from .config import settings


@dataclass
class Summary:
    """Модель данных для хранения результатов суммаризации письма."""
    summary: str
    highlights: List[str]
    suggested_action: str
    sentiment: str
    model: str
    mode: str  # "openrouter" | "deepseek" | "mock"


# Сопоставление рекомендованных действий с категориями
_ACTION_BY_CATEGORY: Dict[str, str] = {
    "urgent": "Эскалировать дежурному инженеру — срочный инцидент.",
    "alerts": "Проверить систему мониторинга, при необходимости создать инцидент.",
    "spam": "Переместить в спам, отправителя — в стоп-лист.",
    "hr_documents": "Передать в HR / согласовать документ.",
    "newsletters": "Информационная рассылка — действий не требуется.",
    "support": "Завести заявку в поддержке и назначить ответственного.",
    "errors": "Письмо нечитаемо — проверить вложение/формат вручную.",
}

# Сопоставление рекомендованных действий с тегами
_ACTION_BY_TAG: Dict[str, str] = {
    "bug": "Воспроизвести проблему и завести баг-репорт.",
    "access": "Проверить права доступа / сбросить учётные данные.",
    "payment": "Передать в бухгалтерию, сверить счёт/оплату.",
    "hardware": "Оформить заявку на диагностику/замену оборудования.",
    "hr": "Согласовать с отделом кадров.",
    "incident": "Эскалировать — затронуты несколько пользователей.",
}

# Регулярные выражения для разбора текста писем при локальной суммаризации
_GREETING_RE: re.Pattern = re.compile(
    r"^\s*(здравствуйте|добрый день|доброе утро|добрый вечер|привет|hi|hello|"
    r"уважаемые коллеги|коллеги|приветствую)[!,. ]*",
    re.IGNORECASE,
)
_SIGN_RE: re.Pattern = re.compile(
    r"^\s*(с уважением|спасибо|заранее спасибо|p\.s\.|br|regards)",
    re.IGNORECASE
)
_DATE_RE: re.Pattern = re.compile(
    r"\b(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}|\d{1,2}:\d{2}|"
    r"до (?:понедельник|вторник|сред|четверг|пятниц|субботы|воскресень|конца недели|завтра)\w*)",
    re.IGNORECASE,
)


def _sentences(text: str) -> List[str]:
    """Разбивает текст на список предложений.

    Args:
        text (str): Исходный текст.

    Returns:
        List[str]: Список предложений.
    """
    parts = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    return [p.strip() for p in parts if p.strip()]


class Summarizer:
    """Класс-адаптер для вызова различных движков суммаризации писем."""

    def summarize(self, subject: str, body: str, category: str, tags: List[str]) -> Summary:
        """Суммаризирует письмо, выбирая доступный движок.

        Args:
            subject (str): Тема письма.
            body (str): Текст письма.
            category (str): Категория письма.
            tags (List[str]): Теги письма.

        Returns:
            Summary: Структурированная сводка.
        """
        if settings.openrouter_enabled:
            try:
                return self._openrouter(subject, body, category, tags)
            except Exception:
                return self._mock(subject, body, category, tags, degraded=True)
        elif settings.ai_enabled:
            try:
                return self._deepseek(subject, body, category, tags)
            except Exception:
                return self._mock(subject, body, category, tags, degraded=True)
        return self._mock(subject, body, category, tags)

    def _openrouter(self, subject: str, body: str, category: str, tags: List[str]) -> Summary:
        """Интеллектуальная суммаризация через API OpenRouter.

        Args:
            subject (str): Тема письма.
            body (str): Текст письма.
            category (str): Категория письма.
            tags (List[str]): Теги письма.

        Returns:
            Summary: Сводка, полученная от LLM на OpenRouter.
        """
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.openrouter_api_key_2,
            timeout=30.0
        )

        system_prompt = (
            "Act as a Senior IT Support Coordinator. Analyze the following incoming support email and provide a structured summary. \n\n"
            "CRITICAL: Each field must start on a new line. Use the following format exactly:\n\n"
            "Проблема: (1-sentence description of the technical problem)\n"
            "ПО: (The specific application or hardware mentioned)\n"
            "Приоритет: (Низкий/Средний/Высокий/Срочный based on business impact)\n"
            "Настроение пользователя: (Briefly describe user's tone)\n"
            "    \n"
            "If the email is not about a technical problem, simply provide a 2-3 sentence summary.\n\n"
            "ANSWER IN THE LANGUAGE OF THE USER. BY DEFAULT ANSWER IN RUSSIAN. \n\n"
            "Email Content:"
        )

        message = f"Subject: {subject}\n\n{body}"

        answer = client.chat.completions.create(
            model=settings.base_model_url,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message}
            ]
        )
        content: str = answer.choices[0].message.content or ""

        # Парсинг структурированного ответа от LLM
        lines = content.splitlines()
        summary_text = ""
        highlights: List[str] = []
        sentiment = "neutral"

        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith("Проблема:"):
                summary_text = line.replace("Проблема:", "").strip()
            elif line.startswith("ПО:"):
                val = line.replace("ПО:", "").strip()
                if val and val.lower() not in ("null", "none", "—", ""):
                    highlights.append(f"ПО: {val}")
            elif line.startswith("Приоритет:"):
                val = line.replace("Приоритет:", "").strip()
                highlights.append(f"Приоритет: {val}")
            elif line.startswith("Настроение пользователя:"):
                val = line.replace("Настроение пользователя:", "").strip()
                highlights.append(f"Настроение: {val}")

                tone = val.lower()
                if any(w in tone for w in ("раздраж", "зло", "плохо", "обеспокоен", "критич", "проблем", "негатив", "ужас")):
                    sentiment = "negative"
                elif any(w in tone for w in ("благодар", "спасибо", "отлич", "рад", "позитив")):
                    sentiment = "positive"
                else:
                    sentiment = "neutral"

        if not summary_text:
            summary_text = content.strip()

        action = _ACTION_BY_TAG.get(tags[0]) if tags else None
        action = action or _ACTION_BY_CATEGORY.get(category, "Обработать в общем порядке.")

        return Summary(
            summary=summary_text,
            highlights=highlights,
            suggested_action=action,
            sentiment=sentiment,
            model=settings.base_model_url,
            mode="openrouter",
        )

    def _mock(self, subject: str, body: str, category: str, tags: List[str], degraded: bool = False) -> Summary:
        """Локальный эвристический суммаризатор без обращения к внешним сетям.

        Args:
            subject (str): Тема письма.
            body (str): Текст письма.
            category (str): Категория письма.
            tags (List[str]): Теги письма.
            degraded (bool): Признак работы после сбоя внешнего ИИ.

        Returns:
            Summary: Сводка, сформированная по локальным эвристикам.
        """
        sents = [s for s in _sentences(body) if not _GREETING_RE.match(s) and not _SIGN_RE.match(s)]
        core = sents[:2] if sents else _sentences(body)[:1]
        summary = " ".join(core) if core else (subject or "Содержимое отсутствует.")
        if subject and subject.lower() not in summary.lower():
            summary = f"«{subject}». {summary}"

        highlights: List[str] = []
        for tag in tags:
            td = TAG_BY_ID.get(tag)
            if td:
                highlights.append(f"Тип проблемы: {td.label}")

        dates = _DATE_RE.findall(body or "")
        if dates:
            highlights.append("Сроки/время: " + ", ".join(dict.fromkeys(dates))[:80])

        if re.search(r"\b(\d+)\s+(сотрудник|пользовател|коллег)", (body or "").lower()):
            highlights.append("Затронуто несколько пользователей")

        if not highlights:
            highlights.append("Дополнительных сущностей не выделено")

        action = _ACTION_BY_TAG.get(tags[0]) if tags else None
        action = action or _ACTION_BY_CATEGORY.get(category, "Обработать в общем порядке.")

        low = (body or "").lower()
        if any(w in low for w in ("срочно", "критичн", "немедленно", "остановлен")):
            sentiment = "negative"
        elif any(w in low for w in ("спасибо", "благодар")):
            sentiment = "positive"
        else:
            sentiment = "neutral"

        return Summary(
            summary=summary.strip(),
            highlights=highlights,
            suggested_action=action,
            sentiment=sentiment,
            model="mock-extractive",
            mode="mock" if not degraded else "mock (fallback после ошибки ИИ)",
        )

    def _deepseek(self, subject: str, body: str, category: str, tags: List[str]) -> Summary:
        """Интеллектуальная суммаризация через API DeepSeek.

        Args:
            subject (str): Тема письма.
            body (str): Текст письма.
            category (str): Категория письма.
            tags (List[str]): Теги письма.

        Returns:
            Summary: Сводка от DeepSeek.
        """
        tag_labels = ", ".join(TAG_BY_ID[t].label for t in tags if t in TAG_BY_ID) or "—"
        system = (
            "Ты — ассистент сотрудника технической поддержки. Кратко суммируй "
            "обращение по-русски и верни СТРОГО JSON с полями: summary (1-2 "
            "предложения), highlights (массив ключевых фактов/сроков), "
            "suggested_action (что сделать сотруднику), sentiment "
            "(positive|neutral|negative)."
        )
        user = (
            f"Тема: {subject}\nКатегория: {category}\nТеги: {tag_labels}\n\n"
            f"Текст письма:\n{body}"
        )
        payload = {
            "model": settings.deepseek_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "stream": False,
        }

        with httpx.Client(timeout=settings.deepseek_timeout) as client:
            resp = client.post(
                f"{settings.deepseek_base_url.rstrip('/')}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
            )
            resp.raise_for_status()
            content: str = resp.json()["choices"][0]["message"]["content"]

        data: Dict[str, Any] = json.loads(content)
        highlights = data.get("highlights") or []
        if isinstance(highlights, str):
            highlights = [highlights]

        return Summary(
            summary=str(data.get("summary", "")).strip(),
            highlights=[str(h) for h in highlights],
            suggested_action=str(data.get("suggested_action", "")).strip(),
            sentiment=str(data.get("sentiment", "neutral")),
            model=settings.deepseek_model,
            mode="deepseek",
        )


summarizer: Summarizer = Summarizer()


def summary_to_dict(s: Summary) -> Dict[str, Any]:
    """Преобразует объект Summary в словарь для JSON-ответа API.

    Args:
        s (Summary): Сводка.

    Returns:
        Dict[str, Any]: Словарь с полями сводки.
    """
    return asdict(s)

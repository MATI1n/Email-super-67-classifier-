"""AI-суммаризатор писем и заявок.

Адаптер ``Summarizer`` строит краткую сводку письма/заявки:
  * при наличии ключа ``DEEPSEEK_API_KEY`` обращается к DeepSeek
    (OpenAI-совместимый /chat/completions);
  * иначе работает локальный экстрактивный режим (mock) — без сети,
    на основе текста письма и результатов классификации.

Контракт ответа одинаков в обоих режимах, поэтому фронтенд не зависит от
того, реальный это AI или mock.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import List, Optional

from .classifier import CATEGORIES, TAG_BY_ID
from .config import settings

# --------------------------------------------------------------------------- #
@dataclass
class Summary:
    summary: str
    highlights: List[str]
    suggested_action: str
    sentiment: str
    model: str
    mode: str  # "deepseek" | "mock"


_ACTION_BY_CATEGORY = {
    "urgent": "Эскалировать дежурному инженеру — срочный инцидент.",
    "alerts": "Проверить систему мониторинга, при необходимости создать инцидент.",
    "spam": "Переместить в спам, отправителя — в стоп-лист.",
    "hr_documents": "Передать в HR / согласовать документ.",
    "newsletters": "Информационная рассылка — действий не требуется.",
    "support": "Завести заявку в поддержке и назначить ответственного.",
    "errors": "Письмо нечитаемо — проверить вложение/формат вручную.",
}
_ACTION_BY_TAG = {
    "bug": "Воспроизвести проблему и завести баг-репорт.",
    "access": "Проверить права доступа / сбросить учётные данные.",
    "payment": "Передать в бухгалтерию, сверить счёт/оплату.",
    "hardware": "Оформить заявку на диагностику/замену оборудования.",
    "hr": "Согласовать с отделом кадров.",
    "incident": "Эскалировать — затронуты несколько пользователей.",
}

_GREETING_RE = re.compile(
    r"^\s*(здравствуйте|добрый день|доброе утро|добрый вечер|привет|hi|hello|"
    r"уважаемые коллеги|коллеги|приветствую)[!,. ]*",
    re.IGNORECASE,
)
_SIGN_RE = re.compile(r"^\s*(с уважением|спасибо|заранее спасибо|p\.s\.|br|regards)",
                      re.IGNORECASE)
_DATE_RE = re.compile(
    r"\b(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}|\d{1,2}:\d{2}|"
    r"до (?:понедельник|вторник|сред|четверг|пятниц|субботы|воскресень|конца недели|завтра)\w*)",
    re.IGNORECASE,
)


def _sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    return [p.strip() for p in parts if p.strip()]


# --------------------------------------------------------------------------- #
class Summarizer:
    def summarize(self, subject: str, body: str, category: str, tags: List[str]) -> Summary:
        if settings.ai_enabled:
            try:
                return self._deepseek(subject, body, category, tags)
            except Exception:
                # Любой сбой сети/квоты — мягкий фолбэк на локальную сводку.
                return self._mock(subject, body, category, tags, degraded=True)
        return self._mock(subject, body, category, tags)

    # ---------------------------- mock ---------------------------------- #
    def _mock(self, subject, body, category, tags, degraded: bool = False) -> Summary:
        sents = [s for s in _sentences(body)
                 if not _GREETING_RE.match(s) and not _SIGN_RE.match(s)]
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
            sentiment = "neutral"
        else:
            sentiment = "neutral"

        return Summary(
            summary=summary.strip(),
            highlights=highlights,
            suggested_action=action,
            sentiment=sentiment,
            model="mock-extractive",
            mode="mock" if not degraded else "mock (fallback после ошибки DeepSeek)",
        )

    # -------------------------- deepseek -------------------------------- #
    def _deepseek(self, subject, body, category, tags) -> Summary:
        import httpx

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
            content = resp.json()["choices"][0]["message"]["content"]

        data = json.loads(content)
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


summarizer = Summarizer()


def summary_to_dict(s: Summary) -> dict:
    return asdict(s)

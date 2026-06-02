"""AI-суммаризатор писем на базе OpenRouter."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any, Dict, List

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
    mode: str  # Всегда "openrouter"


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


class Summarizer:
    """Суммаризатор писем на базе OpenRouter API."""

    def summarize(self, subject: str, body: str, category: str, tags: List[str]) -> Summary:
        """Суммаризирует письмо с помощью OpenRouter API.

        Args:
            subject (str): Тема письма.
            body (str): Текст письма.
            category (str): Категория письма.
            tags (List[str]): Теги письма.

        Returns:
            Summary: Структурированная сводка.
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


summarizer: Summarizer = Summarizer()


def summary_to_dict(s: Summary) -> Dict[str, Any]:
    """Преобразует объект Summary в словарь для JSON-ответа API.

    Args:
        s (Summary): Сводка.

    Returns:
        Dict[str, Any]: Словарь с полями сводки.
    """
    return asdict(s)

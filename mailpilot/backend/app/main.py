"""FastAPI-приложение MailPilot.

Предоставляет REST API для веб-интерфейса почтового клиента (обработка писем,
суммаризация, гибридный поиск, аналитика) и раздает собранные файлы фронтенда.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .ai import summarizer, summary_to_dict
from .classifier import TAG_BY_ID
from .config import settings
from .search import HybridSearch, tokenize
from .store import MailStore


# --------------------------------------------------------------------------- #
# Состояние приложения (хранилище + поисковый индекс)
# --------------------------------------------------------------------------- #
class AppState:
    """Класс для хранения и пересборки глобального состояния приложения."""

    def __init__(self) -> None:
        self.store: Optional[MailStore] = None
        self.search: Optional[HybridSearch] = None

    def rebuild(self) -> None:
        """Перезагружает письма с диска и переиндексирует их для поиска."""
        self.store = MailStore(settings.data_dir)
        self.store.load()
        self.search = HybridSearch(self.store)


state: AppState = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом FastAPI приложения (инициализация при старте)."""
    state.rebuild()
    yield


app: FastAPI = FastAPI(title="MailPilot API", version="1.0.0", lifespan=lifespan)

# Настройка CORS для локальной разработки
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# Схемы запросов Pydantic
# --------------------------------------------------------------------------- #
class ActionRequest(BaseModel):
    """Схема запроса для выполнения действий над письмами."""
    action: str  # read | unread | star | unstar | archive | unarchive | delete | restore


class SummarizeRequest(BaseModel):
    """Схема запроса на суммаризацию письма."""
    scope: str = "email"  # email | ticket


class TagsRequest(BaseModel):
    """Схема запроса для изменения списка тегов письма."""
    tags: List[str]


def _make_snippet(body: str, query: str, width: int = 160) -> str:
    """Генерирует короткий текстовый сниппет вокруг совпадений ключевых слов.

    Args:
        body (str): Текст письма.
        query (str): Поисковый запрос.
        width (int): Максимальная длина сниппета.

    Returns:
        str: Подготовленный сниппет с многоточием.
    """
    terms = tokenize(query)
    low = body.lower()
    pos = -1
    for t in terms:
        p = low.find(t)
        if p != -1:
            pos = p
            break
    if pos == -1:
        text = " ".join(body.split())
        return text[:width] + ("…" if len(text) > width else "")
    start = max(0, pos - width // 3)
    chunk = body[start:start + width].strip()
    return ("…" if start > 0 else "") + " ".join(chunk.split()) + "…"


# --------------------------------------------------------------------------- #
# Служебные эндпойнты
# --------------------------------------------------------------------------- #
@app.get("/api/health")
def health() -> Dict[str, Any]:
    """Проверяет работоспособность сервиса и возвращает состояние бэкенда."""
    return {
        "status": "ok",
        "emails_loaded": state.store.counts()["total"] if state.store else 0,
        "ai_mode": "openrouter" if settings.openrouter_enabled else ("deepseek" if settings.ai_enabled else "mock"),
        "vector_mode": state.search.vector_mode if state.search else "n/a",
    }


@app.post("/api/reset")
def reset() -> Dict[str, Any]:
    """Перезагружает базу писем с диска (полезно для сброса демо-данных)."""
    state.rebuild()
    return {"status": "reloaded", "total": state.store.counts()["total"] if state.store else 0}


@app.get("/api/folders")
def folders() -> Dict[str, Any]:
    """Возвращает информацию о структуре папок и количестве писем в них."""
    if not state.store:
        raise HTTPException(status_code=500, detail="Mail store is not initialized")
    return state.store.counts()


# --------------------------------------------------------------------------- #
# Письма
# --------------------------------------------------------------------------- #
@app.get("/api/emails")
def list_emails(
    folder: str = "inbox",
    category: Optional[str] = None,
    tag: Optional[str] = None,
    unread: bool = False,
    starred: bool = False,
    sort: str = "date",
) -> Dict[str, Any]:
    """Возвращает отфильтрованный и отсортированный список писем.

    Args:
        folder (str): Папка ("inbox", "sent", "archive" и т.д.).
        category (Optional[str]): Фильтр по категории.
        tag (Optional[str]): Фильтр по тегу.
        unread (bool): Только непрочитанные.
        starred (bool): Только помеченные звездочкой.
        sort (str): Тип сортировки ("date" или "priority").

    Returns:
        Dict[str, Any]: Список писем и их общее количество.
    """
    if not state.store:
        raise HTTPException(status_code=500, detail="Mail store is not initialized")
    if tag and tag not in TAG_BY_ID:
        raise HTTPException(status_code=400, detail=f"Неизвестный тег: {tag}")

    items = state.store.query(
        folder=folder,
        category=category,
        tag=tag,
        unread_only=unread,
        starred_only=starred,
    )

    if sort == "priority":
        rank = {"high": 0, "normal": 1, "low": 2}
        items = sorted(items, key=lambda e: (rank.get(e.priority, 1), -e.received_at.timestamp()))

    return {"items": [e.to_list_item() for e in items], "total": len(items)}


@app.get("/api/emails/{mail_id}")
def get_email(mail_id: str, mark_read: bool = True) -> Dict[str, Any]:
    """Возвращает детальную информацию о конкретном письме.

    Args:
        mail_id (str): Идентификатор письма.
        mark_read (bool): Помечать ли письмо прочитанным при открытии.

    Returns:
        Dict[str, Any]: Детальная информация о письме.
    """
    if not state.store:
        raise HTTPException(status_code=500, detail="Mail store is not initialized")
    email = state.store.get(mail_id)
    if not email:
        raise HTTPException(status_code=404, detail="Письмо не найдено")
    if mark_read:
        state.store.mark_read(mail_id, True)
    return email.to_detail()


@app.post("/api/emails/{mail_id}/action")
def email_action(mail_id: str, req: ActionRequest) -> Dict[str, Any]:
    """Выполняет стандартные операции с письмом (архивация, удаление, прочтение).

    Args:
        mail_id (str): Идентификатор письма.
        req (ActionRequest): Параметры действия.

    Returns:
        Dict[str, Any]: Обновленное состояние письма в списке.
    """
    s = state.store
    if not s:
        raise HTTPException(status_code=500, detail="Mail store is not initialized")
    if not s.get(mail_id):
        raise HTTPException(status_code=404, detail="Письмо не найдено")

    a = req.action
    handlers = {
        "read": lambda: s.mark_read(mail_id, True),
        "unread": lambda: s.mark_read(mail_id, False),
        "star": lambda: s.toggle_star(mail_id),
        "unstar": lambda: s.toggle_star(mail_id),
        "archive": lambda: s.archive(mail_id, True),
        "unarchive": lambda: s.archive(mail_id, False),
        "delete": lambda: s.delete(mail_id, True),
        "restore": lambda: s.delete(mail_id, False),
    }

    if a not in handlers:
        raise HTTPException(status_code=400, detail=f"Неизвестное действие: {a}")

    email = handlers[a]()
    return email.to_list_item()


@app.put("/api/emails/{mail_id}/tags")
def set_tags(mail_id: str, req: TagsRequest) -> Dict[str, Any]:
    """Изменяет теги письма.

    Args:
        mail_id (str): Идентификатор письма.
        req (TagsRequest): Запрашиваемый список тегов.

    Returns:
        Dict[str, Any]: Обновленное состояние письма.
    """
    if not state.store:
        raise HTTPException(status_code=500, detail="Mail store is not initialized")
    unknown = [t for t in req.tags if t not in TAG_BY_ID]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Неизвестные теги: {unknown}")

    email = state.store.set_tags(mail_id, req.tags)
    if not email:
        raise HTTPException(status_code=404, detail="Письмо не найдено")
    return email.to_list_item()


# --------------------------------------------------------------------------- #
# AI-суммаризация
# --------------------------------------------------------------------------- #
@app.post("/api/emails/{mail_id}/summarize")
def summarize(mail_id: str, req: SummarizeRequest = SummarizeRequest()) -> Dict[str, Any]:
    """Создает интеллектуальную сводку по письму через LLM.

    Args:
        mail_id (str): Идентификатор письма.
        req (SummarizeRequest): Параметры масштаба сводки (только письмо или вся заявка).

    Returns:
        Dict[str, Any]: Результат суммаризации от LLM.
    """
    if not state.store:
        raise HTTPException(status_code=500, detail="Mail store is not initialized")
    email = state.store.get(mail_id)
    if not email:
        raise HTTPException(status_code=404, detail="Письмо не найдено")

    s = summarizer.summarize(email.subject, email.body, email.category, email.tags)
    result = summary_to_dict(s)
    result["scope"] = req.scope
    result["ticket_id"] = email.ticket_id
    return result


# --------------------------------------------------------------------------- #
# Умный поиск (гибридный: BM25 + семантика)
# --------------------------------------------------------------------------- #
@app.get("/api/search")
def search(q: str = Query(..., min_length=1), top_k: int = 20) -> Dict[str, Any]:
    """Выполняет гибридный лексико-семантический поиск.

    Args:
        q (str): Поисковый запрос.
        top_k (int): Максимальное число возвращаемых результатов.

    Returns:
        Dict[str, Any]: Результаты поиска, информация о векторном режиме и количество.
    """
    if not state.search or not state.store:
        raise HTTPException(status_code=500, detail="Search index is not initialized")

    hits = state.search.search(q, top_k=top_k)
    results = []
    for h in hits:
        email = state.store.get(h.doc_id)
        if not email or email.deleted:
            continue
        item = email.to_list_item()
        item["score"] = h.score
        item["channels"] = h.channels
        item["match_snippet"] = _make_snippet(email.body, q)
        results.append(item)

    return {
        "query": q,
        "vector_mode": state.search.vector_mode,
        "count": len(results),
        "results": results,
    }


# --------------------------------------------------------------------------- #
# Лёгкая аналитика (для дашборда)
# --------------------------------------------------------------------------- #
@app.get("/api/stats")
def stats() -> Dict[str, Any]:
    """Возвращает агрегированную статистику по письмам для дашборда аналитики."""
    if not state.store:
        raise HTTPException(status_code=500, detail="Mail store is not initialized")
    c = state.store.counts()
    active = [e for e in state.store.all() if not e.deleted]
    return {
        "total": c["total"],
        "unread": c["folders"]["inbox_unread"],
        "by_category": c["categories"],
        "by_tag": c["tags"],
        "high_priority": sum(1 for e in active if e.priority == "high"),
        "with_attachments": sum(1 for e in active if e.attachments),
    }


# --------------------------------------------------------------------------- #
# Отдача собранного фронтенда
# --------------------------------------------------------------------------- #
_dist: Path = Path(settings.frontend_dist)
if _dist.exists() and (_dist / "index.html").exists():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="frontend")
else:
    @app.get("/")
    def root() -> Dict[str, str]:
        """Возвращает информацию-заглушку в случае, если фронтенд не собран."""
        return {
            "app": "MailPilot API",
            "docs": "/docs",
            "note": "Фронтенд не собран. Соберите его: cd frontend && npm install && npm run build, "
                    "либо запустите dev-режим: npm run dev (Vite на :5173).",
        }

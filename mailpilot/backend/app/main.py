"""FastAPI-приложение MailPilot.

Отдаёт REST API почтового клиента и (если собран) статический фронтенд.
"""
from __future__ import annotations

import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .ai import summarizer, summary_to_dict
from .classifier import TAG_BY_ID
from .config import settings
from .search import HybridSearch, tokenize
from .store import CATEGORY_LABELS, MailStore

# --------------------------------------------------------------------------- #
# Состояние приложения (хранилище + поисковый индекс).
# --------------------------------------------------------------------------- #
class AppState:
    store: Optional[MailStore] = None
    search: Optional[HybridSearch] = None

    def rebuild(self):
        self.store = MailStore(settings.data_dir)
        self.store.load()
        self.search = HybridSearch(self.store)


state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    state.rebuild()
    yield


app = FastAPI(title="MailPilot API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# Схемы запросов
# --------------------------------------------------------------------------- #
class ActionRequest(BaseModel):
    action: str  # read | unread | star | unstar | archive | unarchive | delete | restore


class SummarizeRequest(BaseModel):
    scope: str = "email"  # email | ticket


class TagsRequest(BaseModel):
    tags: List[str]


def _make_snippet(body: str, query: str, width: int = 160) -> str:
    """Сниппет вокруг первого совпадения слова запроса (для подсветки)."""
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
        "ai_mode": "openrouter",
        "vector_mode": "qdrant",
    }


@app.post("/api/reset")
def reset():
    """Перезагрузить датасет (удобно для демо)."""
    state.rebuild()
    return {"status": "reloaded", "total": state.store.counts()["total"]}


@app.get("/api/folders")
def folders():
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
    sort: str = "date",  # date | priority
):
    if tag and tag not in TAG_BY_ID:
        raise HTTPException(400, f"Неизвестный тег: {tag}")
    items = state.store.query(
        folder=folder, category=category, tag=tag,
        unread_only=unread, starred_only=starred,
    )
    if sort == "priority":
        rank = {"high": 0, "normal": 1, "low": 2}
        items = sorted(items, key=lambda e: (rank.get(e.priority, 1), -e.received_at.timestamp()))
    return {"items": [e.to_list_item() for e in items], "total": len(items)}


@app.get("/api/emails/{mail_id}")
def get_email(mail_id: str, mark_read: bool = True):
    email = state.store.get(mail_id)
    if not email:
        raise HTTPException(404, "Письмо не найдено")
    if mark_read:
        state.store.mark_read(mail_id, True)
    return email.to_detail()


@app.post("/api/emails/{mail_id}/action")
def email_action(mail_id: str, req: ActionRequest):
    s = state.store
    if not s.get(mail_id):
        raise HTTPException(404, "Письмо не найдено")
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
        raise HTTPException(400, f"Неизвестное действие: {a}")
    email = handlers[a]()
    return email.to_list_item()


@app.put("/api/emails/{mail_id}/tags")
def set_tags(mail_id: str, req: TagsRequest):
    unknown = [t for t in req.tags if t not in TAG_BY_ID]
    if unknown:
        raise HTTPException(400, f"Неизвестные теги: {unknown}")
    email = state.store.set_tags(mail_id, req.tags)
    if not email:
        raise HTTPException(404, "Письмо не найдено")
    return email.to_list_item()


# --------------------------------------------------------------------------- #
# AI-суммаризация (письмо / заявка)
# --------------------------------------------------------------------------- #
@app.post("/api/emails/{mail_id}/summarize")
def summarize(mail_id: str, req: SummarizeRequest = SummarizeRequest()):
    email = state.store.get(mail_id)
    if not email:
        raise HTTPException(404, "Письмо не найдено")
    s = summarizer.summarize(email.subject, email.body, email.category, email.tags)
    result = summary_to_dict(s)
    result["scope"] = req.scope
    result["ticket_id"] = email.ticket_id
    return result


# --------------------------------------------------------------------------- #
# Умный поиск (гибридный: BM25 + семантика)
# --------------------------------------------------------------------------- #
@app.get("/api/search")
def search(q: str = Query(..., min_length=1), top_k: int = 3):
    hits = state.search.search(q, top_k=top_k + 10)  # Запрашиваем с запасом на случай удаленных
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
        if len(results) >= top_k:
            break
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
def stats():
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
# Отдача собранного фронтенда (если есть frontend/dist).
# --------------------------------------------------------------------------- #
_dist = Path(settings.frontend_dist)
if _dist.exists() and (_dist / "index.html").exists():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="frontend")
else:
    @app.get("/")
    def root():
        return {
            "app": "MailPilot API",
            "docs": "/docs",
            "note": "Фронтенд не собран. Соберите его: cd frontend && npm install && npm run build, "
                    "либо запустите dev-режим: npm run dev (Vite на :5173).",
        }

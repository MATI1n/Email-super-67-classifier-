"""Умный поиск по ящику.

Гибридный ретрив = лексический канал (BM25) + семантический канал
(векторная БД Coderun). Результаты двух каналов объединяются алгоритмом
Reciprocal Rank Fusion (RRF).

Векторный канал реализован через адаптер ``VectorIndex``:
  * если заданы ключи Coderun (``CODERUN_API_KEY`` + ``CODERUN_BASE_URL``) —
    запросы уходят в реальную векторную БД (см. ``_CoderunBackend``);
  * иначе используется локальный mock-эмбеддер (hashing-векторизация слов и
    символьных триграмм) — демо работает офлайн, а замена на Coderun не
    требует изменений в остальном коде.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from rank_bm25 import BM25Okapi

from .config import settings

# --------------------------------------------------------------------------- #
# Токенизация
# --------------------------------------------------------------------------- #
_TOKEN_RE = re.compile(r"[а-яёa-z0-9]+", re.IGNORECASE)
_STOP = {
    "и", "в", "во", "не", "что", "он", "на", "я", "с", "со", "как", "а", "то",
    "все", "она", "так", "его", "но", "да", "ты", "к", "у", "же", "вы", "за",
    "бы", "по", "ее", "мне", "о", "из", "ему", "the", "a", "to", "of", "and",
    "доброе", "добрый", "день", "здравствуйте", "спасибо", "пожалуйста", "hi",
}


def tokenize(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "") if len(t) > 1 and t.lower() not in _STOP]


def _char_trigrams(token: str) -> List[str]:
    t = f"#{token}#"
    return [t[i:i + 3] for i in range(len(t) - 2)]


# --------------------------------------------------------------------------- #
# Лексический канал: BM25
# --------------------------------------------------------------------------- #
class BM25Channel:
    def __init__(self, doc_ids: List[str], docs: List[str]):
        self.doc_ids = doc_ids
        self._tokens = [tokenize(d) for d in docs]
        self._bm25 = BM25Okapi(self._tokens) if doc_ids else None

    def search(self, query: str, top_k: int) -> List[Tuple[str, float]]:
        if not self._bm25:
            return []
        scores = self._bm25.get_scores(tokenize(query))
        ranked = sorted(zip(self.doc_ids, scores), key=lambda x: x[1], reverse=True)
        return [(i, float(s)) for i, s in ranked if s > 0][:top_k]


# --------------------------------------------------------------------------- #
# Семантический канал: адаптер векторной БД
# --------------------------------------------------------------------------- #
DIM = 2048


def _embed(text: str) -> Dict[int, float]:
    """Локальный mock-эмбеддинг: hashing слов + символьных триграмм.

    Это разреженный нормированный вектор. Символьные триграммы дают
    устойчивость к словоформам («оплата» ~ «оплате»), отличая канал от
    чисто лексического BM25. В проде заменяется эмбеддингами Coderun.
    """
    vec: Dict[int, float] = defaultdict(float)
    tokens = tokenize(text)
    for tok in tokens:
        vec[hash(("w", tok)) % DIM] += 1.0
        for tri in _char_trigrams(tok):
            vec[hash(("t", tri)) % DIM] += 0.5
    norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
    return {k: v / norm for k, v in vec.items()}


def _cosine(a: Dict[int, float], b: Dict[int, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(k, 0.0) for k, v in a.items())


class _LocalVectorBackend:
    """Mock-векторное хранилище в памяти."""

    name = "local-mock"

    def __init__(self):
        self._vectors: Dict[str, Dict[int, float]] = {}

    def index(self, doc_ids: List[str], docs: List[str]) -> None:
        self._vectors = {i: _embed(d) for i, d in zip(doc_ids, docs)}

    def search(self, query: str, top_k: int) -> List[Tuple[str, float]]:
        q = _embed(query)
        scored = [(i, _cosine(q, v)) for i, v in self._vectors.items()]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [(i, float(s)) for i, s in scored if s > 0][:top_k]


class _CoderunBackend:
    """Адаптер реальной векторной БД Coderun (REST).

    Включается, когда заданы CODERUN_API_KEY и CODERUN_BASE_URL. Формы
    запросов вынесены в одно место — при подключении настоящего Coderun
    достаточно поправить пути/поля под его API.
    """

    name = "coderun"

    def __init__(self):
        import httpx  # локальный импорт: нужен только в remote-режиме
        self._httpx = httpx
        self._base = settings.coderun_base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {settings.coderun_api_key}"}
        self._collection = settings.coderun_collection

    def index(self, doc_ids: List[str], docs: List[str]) -> None:
        payload = {"documents": [{"id": i, "text": d} for i, d in zip(doc_ids, docs)]}
        with self._httpx.Client(timeout=settings.coderun_timeout) as client:
            client.post(
                f"{self._base}/collections/{self._collection}/upsert",
                json=payload, headers=self._headers,
            )

    def search(self, query: str, top_k: int) -> List[Tuple[str, float]]:
        with self._httpx.Client(timeout=settings.coderun_timeout) as client:
            resp = client.post(
                f"{self._base}/collections/{self._collection}/search",
                json={"query": query, "top_k": top_k}, headers=self._headers,
            )
            resp.raise_for_status()
            data = resp.json()
        return [(hit["id"], float(hit.get("score", 0.0))) for hit in data.get("results", [])]


class VectorChannel:
    def __init__(self, doc_ids: List[str], docs: List[str]):
        self.backend = _CoderunBackend() if settings.vector_remote else _LocalVectorBackend()
        self.backend.index(doc_ids, docs)

    @property
    def mode(self) -> str:
        return self.backend.name

    def search(self, query: str, top_k: int) -> List[Tuple[str, float]]:
        return self.backend.search(query, top_k)


# --------------------------------------------------------------------------- #
# Гибридный поиск (RRF)
# --------------------------------------------------------------------------- #
@dataclass
class SearchHit:
    doc_id: str
    score: float
    channels: List[str]


class HybridSearch:
    def __init__(self, store):
        self.store = store
        ids, docs = [], []
        for e in store.all():
            ids.append(e.id)
            docs.append(f"{e.subject}\n{e.subject}\n{e.body}")  # тема с двойным весом
        self.bm25 = BM25Channel(ids, docs)
        self.vector = VectorChannel(ids, docs)

    @property
    def vector_mode(self) -> str:
        return self.vector.mode

    def search(self, query: str, top_k: int = 20, pool: int = 50) -> List[SearchHit]:
        if not query.strip():
            return []
        bm = self.bm25.search(query, pool)
        vec = self.vector.search(query, pool)

        k = settings.rrf_k
        scores: Dict[str, float] = defaultdict(float)
        channels: Dict[str, set] = defaultdict(set)

        for rank, (doc_id, _) in enumerate(bm):
            scores[doc_id] += settings.bm25_weight / (k + rank + 1)
            channels[doc_id].add("bm25")
        for rank, (doc_id, _) in enumerate(vec):
            scores[doc_id] += settings.vector_weight / (k + rank + 1)
            channels[doc_id].add("semantic")

        fused = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [
            SearchHit(doc_id=i, score=round(s, 6), channels=sorted(channels[i]))
            for i, s in fused[:top_k]
        ]

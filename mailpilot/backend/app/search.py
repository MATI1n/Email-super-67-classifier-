"""Модуль умного поиска по почтовому ящику.

Реализует гибридный поиск, объединяющий лексический канал (BM25) и
семантический канал на базе векторной БД Qdrant (эмбеддинги Jina v5).
Результаты объединяются алгоритмом Reciprocal Rank Fusion (RRF).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import json
import math
import os
import re
from typing import Any, Dict, List, Set, Tuple

import httpx
from openai import OpenAI
from qdrant_client import QdrantClient, models
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

from .config import settings

# Регулярное выражение для извлечения токенов
_TOKEN_RE: re.Pattern = re.compile(r"[а-яёa-z0-9]+", re.IGNORECASE)

# Список стоп-слов для фильтрации при токенизации
_STOP: Set[str] = {
    "и", "в", "во", "не", "что", "он", "на", "я", "с", "со", "как", "а", "то",
    "все", "она", "так", "его", "но", "да", "ты", "к", "у", "же", "вы", "за",
    "бы", "по", "ее", "мне", "о", "из", "ему", "the", "a", "to", "of", "and",
    "доброе", "добрый", "день", "здравствуйте", "спасибо", "пожалуйста", "hi",
}


def tokenize(text: str) -> List[str]:
    """Разбивает текст на очищенные токены (в нижнем регистре, без стоп-слов).

    Args:
        text (str): Исходный текст.

    Returns:
        List[str]: Список токенов.
    """
    return [
        t.lower()
        for t in _TOKEN_RE.findall(text or "")
        if len(t) > 1 and t.lower() not in _STOP
    ]


class BM25Channel:
    """Канал лексического поиска на основе алгоритма BM25."""

    def __init__(self, doc_ids: List[str], docs: List[str]) -> None:
        """Инициализирует индекс BM25.

        Args:
            doc_ids (List[str]): Список идентификаторов писем.
            docs (List[str]): Список текстов писем.
        """
        self.doc_ids: List[str] = doc_ids
        self._tokens: List[List[str]] = [tokenize(d) for d in docs]
        self._bm25: BM25Okapi | None = BM25Okapi(self._tokens) if doc_ids else None

    def search(self, query: str, top_k: int) -> List[Tuple[str, float]]:
        """Ищет документы по запросу.

        Args:
            query (str): Поисковый запрос.
            top_k (int): Максимальное количество результатов.

        Returns:
            List[Tuple[str, float]]: Список пар (идентификатор документа, оценка).
        """
        if not self._bm25:
            return []
        scores = self._bm25.get_scores(tokenize(query))
        ranked = sorted(zip(self.doc_ids, scores), key=lambda x: x[1], reverse=True)
        return [(i, float(s)) for i, s in ranked if s > 0][:top_k]


class _QdrantBackend:
    """Адаптер векторной БД Qdrant.

    Использует предобученную модель SentenceTransformer для кодирования текстов
    и выполняет гибридный семантический поиск с фильтрацией по метаданным.
    """

    name: str = "qdrant"

    def __init__(self, store: Any) -> None:
        """Инициализирует адаптер Qdrant.

        Args:
            store (MailStore): Ссылка на хранилище писем для получения метаданных.
        """
        self.store: Any = store
        self._qdrant_url: str = f"http://{settings.qdrant_host}:{settings.qdrant_port}"
        self._qdrant_key: str = settings.qdrant_api_key
        self._collection: str = "email_classifier"
        self._client: Any = None
        self._embedder: Any = None

    def _init_clients(self) -> None:
        """Инициализация клиентов Qdrant и SentenceTransformer."""
        if self._client is None:
            import time
            start_time = time.time()
            connected = False
            client = None
            while time.time() - start_time < 30:
                try:
                    client = QdrantClient(
                        url=self._qdrant_url,
                        api_key=self._qdrant_key if self._qdrant_key else None,
                        timeout=5.0
                    )
                    client.get_collections()
                    connected = True
                    break
                except Exception as e:
                    print(f"Waiting for Qdrant at {self._qdrant_url}... Error: {e}")
                    time.sleep(2)
            if not connected:
                print("Could not connect to Qdrant, trying one last time...")
                client = QdrantClient(
                    url=self._qdrant_url,
                    api_key=self._qdrant_key if self._qdrant_key else None
                )
            self._client = client
        if self._embedder is None:
            # Определение локальных путей кэша моделей
            possible_paths = [
                "/app/model_cache/jina-embeddings-v5-omni-nano",
                "model_cache/jina-embeddings-v5-omni-nano",
                "mailpilot/model_cache/jina-embeddings-v5-omni-nano",
                "../model_cache/jina-embeddings-v5-omni-nano",
            ]
            model_path = "jinaai/jina-embeddings-v5-omni-nano"
            for path in possible_paths:
                if os.path.exists(path) and os.path.isdir(path):
                    model_path = path
                    break

            print(f"Loading SentenceTransformer model from: {model_path}")
            self._embedder = SentenceTransformer(
                model_path,
                trust_remote_code=True,
                model_kwargs={"default_task": "retrieval"}
            )

    def index(self, doc_ids: List[str], docs: List[str]) -> None:
        """Индексирует письма в Qdrant с генерацией эмбеддингов Jina.

        Args:
            doc_ids (List[str]): Идентификаторы писем.
            docs (List[str]): Подготовленные тексты для эмбеддингов.
        """
        self._init_clients()

        # Определение размерности эмбеддинга динамически
        test_emb = self._embedder.encode("test")
        dim = len(test_emb)

        # Пересоздаем коллекцию
        self._client.recreate_collection(
            collection_name=self._collection,
            vectors_config=models.VectorParams(
                size=dim,
                distance=models.Distance.COSINE
            )
        )

        points = []
        for idx, (doc_id, text) in enumerate(zip(doc_ids, docs)):
            email_obj = self.store.get(doc_id)
            sender_info = ""
            filename = doc_id
            if email_obj:
                sender_info = f"{email_obj.from_name} {email_obj.from_email}"
                filename = email_obj.filename

            emb = self._embedder.encode(text).tolist()

            points.append(
                models.PointStruct(
                    id=idx,
                    vector=emb,
                    payload={
                        "doc_id": doc_id,
                        "email_name": filename,
                        "sender": sender_info
                    }
                )
            )

        self._client.upsert(
            collection_name=self._collection,
            wait=True,
            points=points
        )

    def _get_query_metadata(self, query: str) -> Dict[str, Any]:
        """Извлекает метаданные (имя/email отправителя) из текстового запроса с помощью LLM OpenRouter.

        Args:
            query (str): Поисковый запрос.

        Returns:
            Dict[str, Any]: Извлеченные данные в формате {"name": ..., "email": ...}.
        """
        client_llm = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.openrouter_api_key_2,
            timeout=30.0
        )

        small_model_prompt = (
            "Extract sender data from a search query into JSON. Rules: 1. Name: nominative case, lowercase. 2. Email: lowercase or null. "
            "Format: {\"name\": \"...\", \"email\": \"...\"}. "
            "Examples: 'найди письмо от Елены Петровой про сайт' -> {\"name\": \"елена петрова\", \"email\": null}; "
            "'поиск сообщений от ivan@mail.com' -> {\"name\": null, \"email\": \"ivan@mail.com\"}; "
            "'письма от Mike' -> {\"name\": \"mike\", \"email\": null}; "
            "'найди письмо от сергея на s.ivanov@test.ru' -> {\"name\": \"сергей\", \"email\": \"s.ivanov@test.ru\"}. "
            "Input: "
        )

        try:
            answer = client_llm.chat.completions.create(
                model=settings.base_model_url,
                messages=[
                    {"role": "system", "content": small_model_prompt},
                    {"role": "user", "content": query}
                ],
                temperature=0
            )
            metadata_str = (answer.choices[0].message.content or "").strip()

            if "```json" in metadata_str:
                metadata_str = metadata_str.split("```json")[1].split("```")[0].strip()
            elif "```" in metadata_str:
                metadata_str = metadata_str.split("```")[1].split("```")[0].strip()

            result: Dict[str, Any] = json.loads(metadata_str)
            return result
        except Exception as e:
            print(f"Metadata extraction error: {e}")
            # Фолбэк на регулярные выражения для поиска email
            email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', query)
            email = email_match.group(0).lower() if email_match else None
            return {"name": None, "email": email}

    def search(self, query: str, top_k: int) -> List[Tuple[str, float]]:
        """Ищет документы в Qdrant с учетом извлеченных LLM фильтров по отправителю.

        Args:
            query (str): Поисковый запрос.
            top_k (int): Максимальное число кандидатов.

        Returns:
            List[Tuple[str, float]]: Найденные документы и косинусные меры близости.
        """
        self._init_clients()

        # Получаем эмбеддинг запроса
        if hasattr(self._embedder, "encode_query"):
            embedded_query = self._embedder.encode_query(query).tolist()
        else:
            embedded_query = self._embedder.encode(query).tolist()

        metadata = self._get_query_metadata(query)
        name = metadata.get("name")
        email = metadata.get("email")

        conditions = []
        if name:
            conditions.append(
                models.FieldCondition(
                    key="sender",
                    match=models.MatchText(text=name)
                )
            )
        if email:
            conditions.append(
                models.FieldCondition(
                    key="sender",
                    match=models.MatchText(text=email)
                )
            )

        qdrant_filter = None
        if conditions:
            qdrant_filter = models.Filter(should=conditions)

        search_result = self._client.query_points(
            collection_name=self._collection,
            query=embedded_query,
            query_filter=qdrant_filter,
            limit=top_k,
            with_payload=True
        )

        hits = []
        for point in search_result.points:
            doc_id = point.payload.get("doc_id")
            score = float(point.score)
            if doc_id:
                hits.append((doc_id, score))
        return hits


class VectorChannel:
    """Семантический векторный канал на базе Qdrant."""

    def __init__(self, store: Any, doc_ids: List[str], docs: List[str]) -> None:
        """Инициализирует канал и строит векторный индекс в Qdrant.

        Args:
            store (MailStore): Хранилище писем.
            doc_ids (List[str]): Список идентификаторов писем.
            docs (List[str]): Список текстов писем.
        """
        self.backend: Any = _QdrantBackend(store)
        self.backend.index(doc_ids, docs)

    @property
    def mode(self) -> str:
        """Возвращает название активного векторного бэкенда."""
        return self.backend.name

    def search(self, query: str, top_k: int) -> List[Tuple[str, float]]:
        """Ищет по векторному индексу.

        Args:
            query (str): Запрос.
            top_k (int): Лимит.

        Returns:
            List[Tuple[str, float]]: Результаты семантического поиска.
        """
        return self.backend.search(query, top_k)


@dataclass
class SearchHit:
    """Итоговый поисковый хит после слияния каналов."""
    doc_id: str
    score: float
    channels: List[str]


class HybridSearch:
    """Основной класс гибридного поиска по почтовому ящику (BM25 + Qdrant + RRF)."""

    def __init__(self, store: Any) -> None:
        """Инициализирует и индексирует все письма из хранилища.

        Args:
            store (MailStore): Объект хранилища писем.
        """
        self.store: Any = store
        ids, docs = [], []
        for e in store.all():
            ids.append(e.id)
            docs.append(f"{e.subject}\n{e.subject}\n{e.body}")  # Тема с двойным весом
        self.bm25: BM25Channel = BM25Channel(ids, docs)
        self.vector: VectorChannel = VectorChannel(store, ids, docs)

    @property
    def vector_mode(self) -> str:
        """Возвращает активный режим векторного поиска."""
        return self.vector.mode

    def search(self, query: str, top_k: int = 20, pool: int = 50) -> List[SearchHit]:
        """Выполняет гибридный поиск по запросу с применением Reciprocal Rank Fusion.

        Args:
            query (str): Поисковый запрос.
            top_k (int): Число возвращаемых документов.
            pool (int): Глубина выборки из каждого канала перед слиянием.

        Returns:
            List[SearchHit]: Отсортированный список гибридных хитов.
        """
        if not query.strip():
            return []
        bm = self.bm25.search(query, pool)
        vec = self.vector.search(query, pool)

        k = settings.rrf_k
        scores: Dict[str, float] = defaultdict(float)
        channels: Dict[str, Set[str]] = defaultdict(set)

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

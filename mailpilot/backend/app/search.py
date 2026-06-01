"""Модуль умного поиска по почтовому ящику.

Реализует гибридный поиск, объединяющий лексический канал (BM25) и
семантический канал (векторная база данных Qdrant или Coderun с фолбэком на локальный хэш-эмбеддер).
Результаты объединяются алгоритмом Reciprocal Rank Fusion (RRF).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import json
import math
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


def _char_trigrams(token: str) -> List[str]:
    """Выделяет символьные триграммы из токена для устойчивости поиска.

    Args:
        token (str): Токен.

    Returns:
        List[str]: Список триграмм.
    """
    t = f"#{token}#"
    return [t[i:i + 3] for i in range(len(t) - 2)]


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


# Размерность mock-эмбеддинга
DIM: int = 2048


def _embed(text: str) -> Dict[int, float]:
    """Строит разреженный нормализованный mock-эмбеддинг на основе hashing.

    Args:
        text (str): Исходный текст.

    Returns:
        Dict[int, float]: Разреженный вектор (хэш -> вес).
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
    """Вычисляет косинусное сходство между двумя разреженными векторами.

    Args:
        a (Dict[int, float]): Первый вектор.
        b (Dict[int, float]): Второй вектор.

    Returns:
        float: Косинусное сходство.
    """
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(k, 0.0) for k, v in a.items())


class _LocalVectorBackend:
    """Локальное векторное хранилище в оперативной памяти (mock)."""

    name: str = "local-mock"

    def __init__(self) -> None:
        self._vectors: Dict[str, Dict[int, float]] = {}

    def index(self, doc_ids: List[str], docs: List[str]) -> None:
        """Индексирует тексты документов локально.

        Args:
            doc_ids (List[str]): Список идентификаторов писем.
            docs (List[str]): Список текстов писем.
        """
        self._vectors = {i: _embed(d) for i, d in zip(doc_ids, docs)}

    def search(self, query: str, top_k: int) -> List[Tuple[str, float]]:
        """Локальный векторный поиск по косинусному сходству.

        Args:
            query (str): Поисковый запрос.
            top_k (int): Максимальное количество результатов.

        Returns:
            List[Tuple[str, float]]: Результаты поиска.
        """
        q = _embed(query)
        scored = [(i, _cosine(q, v)) for i, v in self._vectors.items()]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [(i, float(s)) for i, s in scored if s > 0][:top_k]


class _CoderunBackend:
    """Адаптер внешней векторной БД Coderun."""

    name: str = "coderun"

    def __init__(self) -> None:
        self._base: str = settings.coderun_base_url.rstrip("/")
        self._headers: Dict[str, str] = {"Authorization": f"Bearer {settings.coderun_api_key}"}
        self._collection: str = settings.coderun_collection

    def index(self, doc_ids: List[str], docs: List[str]) -> None:
        """Загружает документы во внешнюю векторную БД Coderun.

        Args:
            doc_ids (List[str]): Идентификаторы.
            docs (List[str]): Тексты.
        """
        payload = {"documents": [{"id": i, "text": d} for i, d in zip(doc_ids, docs)]}
        with httpx.Client(timeout=settings.coderun_timeout) as client:
            client.post(
                f"{self._base}/collections/{self._collection}/upsert",
                json=payload,
                headers=self._headers,
            )

    def search(self, query: str, top_k: int) -> List[Tuple[str, float]]:
        """Ищет похожие документы в Coderun.

        Args:
            query (str): Запрос.
            top_k (int): Лимит.

        Returns:
            List[Tuple[str, float]]: Результаты.
        """
        with httpx.Client(timeout=settings.coderun_timeout) as client:
            resp = client.post(
                f"{self._base}/collections/{self._collection}/search",
                json={"query": query, "top_k": top_k},
                headers=self._headers,
            )
            resp.raise_for_status()
            data = resp.json()
        return [(hit["id"], float(hit.get("score", 0.0))) for hit in data.get("results", [])]


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
        self._qdrant_url: str = "https://5579278d-b04b-4fbd-9539-a97af90de739.europe-west3-0.gcp.cloud.qdrant.io"
        self._qdrant_key: str = settings.qdrant_api_key
        self._collection: str = "email_classifier"
        self._client: Any = None
        self._embedder: Any = None

    def _init_clients(self) -> None:
        """Инициализация клиентов Qdrant и SentenceTransformer."""
        if self._client is None:
            self._client = QdrantClient(
                location=self._qdrant_url,
                api_key=self._qdrant_key
            )
        if self._embedder is None:
            import os
            # Possible paths to load from volume/local cache
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
        """Извлекает метаданные (имя/email отправителя) из текстового запроса с помощью LLM.

        Args:
            query (str): Поисковый запрос.

        Returns:
            Dict[str, Any]: Извлеченные данные в формате {"name": ..., "email": ...}.
        """
        api_key = settings.openrouter_api_key_2 or settings.deepseek_api_key
        base_url = "https://openrouter.ai/api/v1" if settings.openrouter_api_key_2 else settings.deepseek_base_url
        model = settings.base_model_url or settings.deepseek_model

        if not api_key:
            return {"name": None, "email": None}

        client_llm = OpenAI(
            base_url=base_url,
            api_key=api_key,
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
                model=model,
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
    """Универсальный векторный канал, инкапсулирующий бэкенд (Qdrant, Coderun или Mock)."""

    def __init__(self, store: Any, doc_ids: List[str], docs: List[str]) -> None:
        """Инициализирует канал и строит векторный индекс.

        Args:
            store (MailStore): Хранилище писем.
            doc_ids (List[str]): Список идентификаторов писем.
            docs (List[str]): Список текстов писем.
        """
        if settings.qdrant_enabled:
            self.backend: Any = _QdrantBackend(store)
        elif settings.vector_remote:
            self.backend = _CoderunBackend()
        else:
            self.backend = _LocalVectorBackend()
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
    """Основной класс гибридного поиска по почтовому ящику (BM25 + Векторы + RRF)."""

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

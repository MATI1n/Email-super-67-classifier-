"""Конфигурация приложения MailPilot.

Все внешние сервисы (OpenRouter, DeepSeek, векторные БД Qdrant и Coderun)
настраиваются через переменные окружения. При отсутствии ключей
приложение автоматически переходит в mock-режим.
"""
from __future__ import annotations

from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT: Path = Path(__file__).resolve().parent.parent  # .../backend


class Settings(BaseSettings):
    """Класс настроек конфигурации приложения на основе Pydantic Settings."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- AI-суммаризатор: DeepSeek (OpenAI-совместимый API) ---
    deepseek_api_key: str = Field(default="", description="API ключ для DeepSeek")
    deepseek_base_url: str = Field(default="https://api.deepseek.com", description="Базовый URL API DeepSeek")
    deepseek_model: str = Field(default="deepseek-chat", description="Модель DeepSeek")
    deepseek_timeout: float = Field(default=30.0, description="Таймаут запросов к DeepSeek в секундах")

    # --- OpenRouter & Qdrant (Part 3) ---
    openrouter_api_key_2: str = Field(default="", description="API ключ для OpenRouter")
    base_model_url: str = Field(default="", description="Идентификатор модели на OpenRouter")
    qdrant_api_key: str = Field(default="", description="API ключ для Qdrant Cloud")

    # --- Векторная БД Coderun (семантический поиск) ---
    coderun_api_key: str = Field(default="", description="API ключ для Coderun")
    coderun_base_url: str = Field(default="", description="Базовый URL Coderun API")
    coderun_collection: str = Field(default="mailpilot-emails", description="Имя коллекции в Coderun")
    coderun_timeout: float = Field(default=15.0, description="Таймаут запросов к Coderun в секундах")

    # --- Параметры гибридного поиска ---
    rrf_k: int = Field(default=60, description="Параметр K для алгоритма Reciprocal Rank Fusion (RRF)")
    bm25_weight: float = Field(default=1.0, description="Вес лексического канала поиска (BM25)")
    vector_weight: float = Field(default=1.0, description="Вес семантического векторного канала поиска")

    # --- Директории данных ---
    data_dir: str = Field(default=str(BACKEND_ROOT / "app" / "data" / "inbox"), description="Путь к входящим письмам")
    frontend_dist: str = Field(default=str(BACKEND_ROOT.parent / "frontend" / "dist"), description="Путь к собранному фронтенду")

    @property
    def ai_enabled(self) -> bool:
        """Определяет, доступен ли какой-либо внешний сервис искусственного интеллекта."""
        return bool(self.deepseek_api_key.strip() or self.openrouter_api_key_2.strip())

    @property
    def openrouter_enabled(self) -> bool:
        """Определяет, заданы ли настройки для интеграции с OpenRouter."""
        return bool(self.openrouter_api_key_2.strip())

    @property
    def vector_remote(self) -> bool:
        """Определяет, настроена ли внешняя векторная база данных (Coderun или Qdrant)."""
        return bool((self.coderun_api_key.strip() and self.coderun_base_url.strip()) or self.qdrant_api_key.strip())

    @property
    def qdrant_enabled(self) -> bool:
        """Определяет, настроена ли интеграция с базой данных Qdrant."""
        return bool(self.qdrant_api_key.strip())


settings = Settings()


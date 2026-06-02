"""Конфигурация приложения MailPilot."""
from __future__ import annotations

from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT: Path = Path(__file__).resolve().parent.parent  # .../backend


class Settings(BaseSettings):
    """Класс настроек конфигурации приложения на основе Pydantic Settings."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- AI-суммаризатор (OpenRouter) ---
    openrouter_api_key_2: str = Field(default="", description="API ключ для OpenRouter")
    base_model_url: str = Field(default="google/gemini-2.5-flash", description="Идентификатор модели на OpenRouter")

    # --- Семантический поиск (Qdrant) ---
    qdrant_host: str = Field(default="localhost", description="Хост базы данных Qdrant")
    qdrant_port: int = Field(default=6333, description="Порт базы данных Qdrant")
    qdrant_api_key: str = Field(default="", description="API ключ для Qdrant (если требуется)")

    # --- Гибридный поиск RRF ---
    rrf_k: int = Field(default=60, description="Параметр сглаживания RRF")
    bm25_weight: float = Field(default=1.0, description="Вес BM25 канала")
    vector_weight: float = Field(default=1.0, description="Вес векторного канала")

    # --- Директории данных ---
    data_dir: str = Field(default=str(BACKEND_ROOT / "app" / "data" / "inbox"), description="Путь к входящим письмам")
    frontend_dist: str = Field(default=str(BACKEND_ROOT.parent / "frontend" / "dist"), description="Путь к собранному фронтенду")


settings = Settings()

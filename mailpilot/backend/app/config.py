"""Конфигурация приложения.

Все внешние сервисы (DeepSeek, векторная БД Coderun) подключаются через
переменные окружения. Если ключей нет — модули автоматически работают в
mock-режиме, поэтому демо запускается «из коробки», а реальные ключи
вставляются позже без правки кода.
"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent  # .../backend


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- AI-суммаризатор: DeepSeek (OpenAI-совместимый API) ---
    # Пусто -> mock-режим (экстрактивная сводка без сети).
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    deepseek_timeout: float = 30.0

    # --- Векторная БД Coderun (семантический поиск) ---
    # Пусто -> локальные mock-эмбеддинги (hashing-векторизация).
    coderun_api_key: str = ""
    coderun_base_url: str = ""
    coderun_collection: str = "mailpilot-emails"
    coderun_timeout: float = 15.0

    # --- Гибридный поиск ---
    # k для Reciprocal Rank Fusion и веса каналов.
    rrf_k: int = 60
    bm25_weight: float = 1.0
    vector_weight: float = 1.0

    # --- Данные ---
    data_dir: str = str(BACKEND_ROOT / "app" / "data" / "inbox")
    frontend_dist: str = str(BACKEND_ROOT.parent / "frontend" / "dist")

    @property
    def ai_enabled(self) -> bool:
        """Реальный DeepSeek доступен?"""
        return bool(self.deepseek_api_key.strip())

    @property
    def vector_remote(self) -> bool:
        """Реальная векторная БД Coderun доступна?"""
        return bool(self.coderun_api_key.strip() and self.coderun_base_url.strip())


settings = Settings()

from __future__ import annotations

import logging
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # LLM
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    # Storage
    chroma_persist_dir: str = "./data/chroma"
    memory_dir: str = "./data/memory"

    # Logging
    log_level: str = "INFO"

    # Data sources
    fbi_api_key: str = ""
    newsapi_key: str = ""

    # Langfuse
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_base_url: str = "http://localhost:3000"
    langfuse_enabled: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def ensure_data_dirs(self) -> None:
        """Create data directories if they don't exist."""
        Path(self.chroma_persist_dir).mkdir(parents=True, exist_ok=True)
        Path(self.memory_dir).mkdir(parents=True, exist_ok=True)


settings = Settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

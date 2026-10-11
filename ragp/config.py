"""Runtime configuration from environment variables, read when Settings() is created."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _env(name: str, default: str) -> field:
    return field(default_factory=lambda: os.getenv(name, default))


def _api_keys() -> dict[str, str]:
    """API_KEYS="key:role,key:role" maps API keys to roles (simulates SSO group mapping)."""
    raw = os.getenv("API_KEYS", "operator-key:operator,analyst-key:qa_analyst,head-key:qa_head")
    pairs = [p.split(":", 1) for p in raw.split(",") if ":" in p]
    return {k.strip(): r.strip() for k, r in pairs}


@dataclass(frozen=True)
class Settings:
    env: str = _env("APP_ENV", "dev")
    database_url: str = _env("DATABASE_URL", f"sqlite:///{ROOT / 'data' / 'rag.db'}")
    corpus_dir: str = _env("CORPUS_DIR", str(ROOT / "corpus"))
    embeddings: str = _env("EMBEDDINGS", "lsa")            # lsa (offline) | fastembed (BAAI/bge-small-en-v1.5)
    llm_provider: str = _env("LLM_PROVIDER", "auto")
    llm_model: str = _env("LLM_MODEL", "")
    llm_base_url: str = _env("LLM_BASE_URL", "")
    llm_api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", os.getenv("GROQ_API_KEY", "")))
    llm_timeout_s: float = field(default_factory=lambda: float(os.getenv("LLM_TIMEOUT_S", "30")))
    top_k: int = field(default_factory=lambda: int(os.getenv("TOP_K", "5")))
    min_support: float = field(default_factory=lambda: float(os.getenv("MIN_SUPPORT", "0.5")))
    api_keys: dict[str, str] = field(default_factory=_api_keys)


def get_settings() -> Settings:
    return Settings()

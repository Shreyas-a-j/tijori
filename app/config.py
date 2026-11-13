"""Process-wide configuration, loaded from environment variables.

Defaults target a local Ollama instance so the demo needs no internet.
See .env.example and CONTRACT.md §7.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_env_file(path: Path) -> None:
    """Populate ``os.environ`` from a ``KEY=VALUE`` file (stdlib only).

    Values already present in the real environment win, so an exported variable
    always overrides the file. Set ``TIJORI_DISABLE_DOTENV=1`` to skip loading
    entirely, which keeps the test suite hermetic.
    """

    if os.getenv("TIJORI_DISABLE_DOTENV") or not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip('"').strip("'")


_load_env_file(ROOT / ".env")


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value not in (None, "") else default


@dataclass(frozen=True)
class Settings:
    llm_provider: str = _env("TIJORI_LLM_PROVIDER", "openai_compatible")
    llm_base_url: str = _env("TIJORI_LLM_BASE_URL", "http://127.0.0.1:11434/v1")
    llm_api_key: str = _env("TIJORI_LLM_API_KEY", "ollama")
    llm_model: str = _env("TIJORI_LLM_MODEL", "qwen2.5:3b")
    llm_timeout_s: float = float(_env("TIJORI_LLM_TIMEOUT_S", "120"))
    llm_temperature: float = float(_env("TIJORI_LLM_TEMPERATURE", "0.2"))
    llm_max_tokens: int = int(_env("TIJORI_LLM_MAX_TOKENS", "512"))

    db_path: str = _env("TIJORI_DB_PATH", "data/audit.db")
    api_url: str = _env("TIJORI_API_URL", "http://127.0.0.1:8000")
    max_input_chars: int = int(_env("TIJORI_MAX_INPUT_CHARS", "100000"))
    log_level: str = _env("TIJORI_LOG_LEVEL", "INFO")
    api_key: str = _env("TIJORI_API_KEY", "")
    audit_retention_days: int = int(_env("TIJORI_AUDIT_RETENTION_DAYS", "365"))

    # On-device intake (UI process only; the gateway never loads this model).
    translate_model: str = _env(
        "TIJORI_TRANSLATE_MODEL", "facebook/nllb-200-distilled-600M"
    )
    translate_enabled: bool = _env("TIJORI_TRANSLATE_ENABLED", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def get_translate_model() -> str:
    """Read the NLLB model id dynamically so tests can override it."""

    return _env("TIJORI_TRANSLATE_MODEL", settings.translate_model)


def get_translate_enabled() -> bool:
    """Read the kill switch dynamically (TIJORI_TRANSLATE_ENABLED=0)."""

    return _env("TIJORI_TRANSLATE_ENABLED", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def get_api_key() -> str:
    """Read API key dynamically so an unset variable disables authentication.

    Allows tests to toggle API key via monkeypatch.setenv.
    """
    return os.getenv("TIJORI_API_KEY", "")


def get_audit_retention_days() -> int:
    """Read retention days dynamically from environment, falling back to settings."""
    val = os.getenv("TIJORI_AUDIT_RETENTION_DAYS")
    if val not in (None, ""):
        return int(val)
    return settings.audit_retention_days


settings = Settings()

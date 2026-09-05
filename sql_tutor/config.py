from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv


class ConfigurationError(ValueError):
    pass


def _int(name: str, default: int, minimum: int = 1) -> int:
    value = os.getenv(name, str(default))
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc
    if parsed < minimum:
        raise ConfigurationError(f"{name} must be >= {minimum}")
    return parsed


@dataclass(frozen=True)
class Settings:
    database_app_url: str
    database_runner_url: str
    database_evaluator_url: str
    database_admin_url: str | None
    llm_base_url: str | None
    llm_model: str | None
    llm_api_key: str | None
    llm_timeout_seconds: int = 30
    llm_max_attempts: int = 3
    sql_timeout_ms: int = 3000
    sql_lock_timeout_ms: int = 1000
    sql_max_chars: int = 20000
    display_row_limit: int = 200
    evaluation_row_limit: int = 2000
    result_byte_limit: int = 2097152
    streamlit_server_address: str = "127.0.0.1"

    @classmethod
    def from_env(cls, env_file: str | Path | None = None, *, require_database: bool = True, require_admin: bool = False) -> "Settings":
        if env_file:
            load_dotenv(env_file, override=False)
        required = ["DATABASE_APP_URL", "DATABASE_RUNNER_URL", "DATABASE_EVALUATOR_URL"]
        if require_admin:
            required.append("DATABASE_ADMIN_URL")
        missing = [name for name in required if require_database and not os.getenv(name)]
        if missing:
            raise ConfigurationError("Missing required environment variables: " + ", ".join(missing))
        settings = cls(
            database_app_url=os.getenv("DATABASE_APP_URL", ""),
            database_runner_url=os.getenv("DATABASE_RUNNER_URL", ""),
            database_evaluator_url=os.getenv("DATABASE_EVALUATOR_URL", ""),
            database_admin_url=os.getenv("DATABASE_ADMIN_URL"),
            llm_base_url=os.getenv("LLM_BASE_URL") or None,
            llm_model=os.getenv("LLM_MODEL") or None,
            llm_api_key=os.getenv("LLM_API_KEY") or None,
            llm_timeout_seconds=_int("LLM_TIMEOUT_SECONDS", 30),
            llm_max_attempts=_int("LLM_MAX_ATTEMPTS", 3),
            sql_timeout_ms=_int("SQL_TIMEOUT_MS", 3000),
            sql_lock_timeout_ms=_int("SQL_LOCK_TIMEOUT_MS", 1000),
            sql_max_chars=_int("SQL_MAX_CHARS", 20000),
            display_row_limit=_int("DISPLAY_ROW_LIMIT", 200),
            evaluation_row_limit=_int("EVALUATION_ROW_LIMIT", 2000),
            result_byte_limit=_int("RESULT_BYTE_LIMIT", 2097152),
            streamlit_server_address=os.getenv("STREAMLIT_SERVER_ADDRESS", "127.0.0.1"),
        )
        if require_database:
            settings.validate_urls()
            if require_admin:
                settings.validate_bootstrap_passwords()
        return settings

    def validate_urls(self) -> None:
        for name, value in (("DATABASE_APP_URL", self.database_app_url), ("DATABASE_RUNNER_URL", self.database_runner_url), ("DATABASE_EVALUATOR_URL", self.database_evaluator_url)):
            if not value or urlparse(value).scheme not in {"postgresql", "postgres"}:
                raise ConfigurationError(f"{name} must be a PostgreSQL URL")

    def validate_bootstrap_passwords(self) -> None:
        pairs = {
            "DATABASE_ADMIN_URL": (self.database_admin_url, ("SQL_MENTOR_POSTGRES_PASSWORD", "TUTOR_POSTGRES_OWNER_PASSWORD")),
            "DATABASE_APP_URL": (self.database_app_url, ("SQL_MENTOR_APP_PASSWORD", "TUTOR_APP_PASSWORD")),
            "DATABASE_RUNNER_URL": (self.database_runner_url, ("SQL_MENTOR_SANDBOX_PASSWORD", "TUTOR_RUNNER_PASSWORD")),
            "DATABASE_EVALUATOR_URL": (self.database_evaluator_url, ("SQL_MENTOR_EVALUATOR_PASSWORD", "TUTOR_EVALUATOR_PASSWORD")),
        }
        for url_name, (url, env_names) in pairs.items():
            if not url:
                raise ConfigurationError(f"{url_name} must be configured")
            expected = next((os.getenv(name) for name in env_names if os.getenv(name) is not None), None)
            if expected is not None and unquote(urlparse(url).password or "") != expected:
                raise ConfigurationError(f"{url_name} password does not match the configured bootstrap password")

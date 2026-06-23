from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str | None = None
    openai_model: str = "gpt-5-mini"
    agent_dry_run: bool = True
    max_diff_chars: int = 40_000
    max_doc_chars: int = 12_000
    allowed_doc_dirs: str = "docs,README.md"
    repository_root: str = "."

    @property
    def allowed_paths(self) -> tuple[str, ...]:
        return tuple(part.strip() for part in self.allowed_doc_dirs.split(",") if part.strip())

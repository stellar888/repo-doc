from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, Field
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


class ProjectConfig(BaseModel):
    """Optional repo-doc.toml settings committed by a target repository."""

    allowed_doc_paths: list[str] | None = Field(default=None, min_length=1)
    base_branch: str | None = None
    max_diff_chars: int | None = Field(default=None, gt=0)
    max_doc_chars: int | None = Field(default=None, gt=0)
    openai_model: str | None = None


def load_project_config(repo_root: Path, config_file: Path | None = None) -> ProjectConfig:
    path = config_file or repo_root / "repo-doc.toml"
    if not path.exists():
        return ProjectConfig()

    with path.open("rb") as file:
        raw = tomllib.load(file)

    if "tool" in raw and isinstance(raw["tool"], dict):
        tool_config = raw["tool"].get("repo-doc")
        if isinstance(tool_config, dict):
            raw = tool_config

    return ProjectConfig.model_validate(raw)


def apply_project_config(settings: Settings, config: ProjectConfig) -> Settings:
    if config.allowed_doc_paths:
        settings.allowed_doc_dirs = ",".join(config.allowed_doc_paths)
    if config.max_diff_chars is not None:
        settings.max_diff_chars = config.max_diff_chars
    if config.max_doc_chars is not None:
        settings.max_doc_chars = config.max_doc_chars
    if config.openai_model:
        settings.openai_model = config.openai_model
    return settings

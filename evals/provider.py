"""Promptfoo Python provider that evaluates the complete application graph."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from repo_doc_agent.config import Settings  # noqa: E402
from repo_doc_agent.graph import run_agent  # noqa: E402
from repo_doc_agent.model import MockStructuredModel, OpenAIStructuredModel  # noqa: E402


def call_api(prompt: str, options: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    config = options.get("config", {})
    use_mock = bool(config.get("mock", False))
    settings = Settings()
    model = MockStructuredModel() if use_mock else OpenAIStructuredModel(settings)
    result = run_agent(diff=prompt, settings=settings, model=model)
    return {
        "output": result.model_dump_json(),
        "metadata": {
            "status": result.status,
            "prompt_version": result.prompt_version,
            "model": result.model,
        },
    }

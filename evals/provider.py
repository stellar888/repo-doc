"""Promptfoo Python provider that evaluates the complete application graph."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from repo_doc_agent.config import Settings  # noqa: E402
from repo_doc_agent.contract import render_agent_json_result  # noqa: E402
from repo_doc_agent.graph import run_agent  # noqa: E402
from repo_doc_agent.model import MockStructuredModel, OpenAIStructuredModel  # noqa: E402


def _settings_from_config(config: dict[str, Any]) -> Settings:
    settings = Settings()
    if repo_root := config.get("repo_root"):
        settings.repository_root = str(repo_root)
    if allowed_paths := config.get("allowed_paths"):
        settings.allowed_doc_dirs = ",".join(str(path) for path in allowed_paths)
    if "include_agents_doc" in config:
        settings.include_agents_doc = bool(config["include_agents_doc"])
    if max_diff_chars := config.get("max_diff_chars"):
        settings.max_diff_chars = int(max_diff_chars)
    if max_doc_chars := config.get("max_doc_chars"):
        settings.max_doc_chars = int(max_doc_chars)
    if openai_model := config.get("openai_model"):
        settings.openai_model = str(openai_model)
    return settings


def call_api(prompt: str, options: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    del context
    config = options.get("config", {})
    use_mock = bool(config.get("mock", False))
    output_format = str(config.get("output_format", "agent-json"))
    settings = _settings_from_config(config)
    model = MockStructuredModel() if use_mock else OpenAIStructuredModel(settings)
    result = run_agent(diff=prompt, settings=settings, model=model)
    if output_format == "agent-json":
        output = render_agent_json_result(result)
        parsed = json.loads(output)
    elif output_format == "json":
        output = result.model_dump_json()
        parsed = result.model_dump(mode="json")
    else:
        raise ValueError("Promptfoo provider output_format must be agent-json or json.")

    return {
        "output": output,
        "metadata": {
            "status": result.status,
            "action": result.proposal.action,
            "next_action": parsed.get("next_action"),
            "check_exit_code": parsed.get("check_exit_code"),
            "prompt_version": result.prompt_version,
            "model": result.model,
        },
    }

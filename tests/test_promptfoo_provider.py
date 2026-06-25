import importlib.util
import json
from pathlib import Path
from types import ModuleType


def _load_provider() -> ModuleType:
    provider_path = Path(__file__).resolve().parents[1] / "evals" / "provider.py"
    spec = importlib.util.spec_from_file_location("repo_doc_promptfoo_provider", provider_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_promptfoo_provider_emits_agent_json_contract() -> None:
    provider = _load_provider()

    response = provider.call_api(
        """
diff --git a/src/api.py b/src/api.py
+@app.get("/v1/widgets")
+def list_widgets():
+    return {"items": []}
""".strip(),
        {"config": {"mock": True, "output_format": "agent-json"}},
        {},
    )

    payload = json.loads(response["output"])
    assert payload["schema_version"] == 1
    assert payload["status"] == "ok"
    assert payload["next_action"] == "update_documentation"
    assert payload["check_exit_code"] == 2
    assert payload["can_apply"] is True
    assert payload["edit_paths"] == ["docs/api.md"]
    assert response["metadata"]["next_action"] == "update_documentation"


def test_promptfoo_provider_can_include_agents_doc() -> None:
    provider = _load_provider()

    response = provider.call_api(
        """
diff --git a/src/repo_doc_agent/cli.py b/src/repo_doc_agent/cli.py
+# Codex coding agent workflow guidance changed.
""".strip(),
        {
            "config": {
                "mock": True,
                "output_format": "agent-json",
                "include_agents_doc": True,
            }
        },
        {},
    )

    payload = json.loads(response["output"])
    assert payload["next_action"] == "update_documentation"
    assert payload["edit_paths"] == ["AGENTS.md"]

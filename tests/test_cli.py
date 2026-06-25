import json
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from repo_doc_agent.cli import _load_diff, _render_agent_json_result, _render_markdown_result, app
from repo_doc_agent.config import Settings, apply_project_config, load_project_config
from repo_doc_agent.schemas import AgentResult, DocumentationProposal, Finding, ImpactAnalysis

runner = CliRunner()


def test_version_option_reports_package_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert "repo-doc 0.5.0" in result.output


def test_init_creates_detected_project_config(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")

    result = runner.invoke(
        app,
        ["init", "--repo-root", str(tmp_path), "--include-agents-doc", "--base-branch", "main"],
    )

    assert result.exit_code == 0
    config = (tmp_path / "repo-doc.toml").read_text(encoding="utf-8")
    assert 'allowed_doc_paths = ["docs", "README.md"]' in config
    assert "include_agents_doc = true" in config
    assert 'base_branch = "main"' in config


def test_init_refuses_to_overwrite_existing_config(tmp_path: Path) -> None:
    config_file = tmp_path / "repo-doc.toml"
    config_file.write_text("base_branch = \"main\"\n", encoding="utf-8")

    result = runner.invoke(app, ["init", "--repo-root", str(tmp_path)])

    assert result.exit_code == 1
    assert config_file.read_text(encoding="utf-8") == 'base_branch = "main"\n'


def test_init_force_overwrites_with_explicit_doc_paths(tmp_path: Path) -> None:
    config_file = tmp_path / "repo-doc.toml"
    config_file.write_text("base_branch = \"old\"\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "init",
            "--repo-root",
            str(tmp_path),
            "--allowed-doc-path",
            "docs",
            "--allowed-doc-path",
            "guides",
            "--base-branch",
            "origin/main",
            "--force",
        ],
    )

    assert result.exit_code == 0
    config = config_file.read_text(encoding="utf-8")
    assert 'allowed_doc_paths = ["docs", "guides"]' in config
    assert 'base_branch = "origin/main"' in config


def test_init_ci_creates_github_actions_workflow(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "init",
            "--repo-root",
            str(tmp_path),
            "--ci",
            "--ci-mock",
            "--include-agents-doc",
            "--action-ref",
            "stellar888/repo-doc@v0.5.0",
        ],
    )

    assert result.exit_code == 0
    workflow = (tmp_path / ".github" / "workflows" / "repo-doc.yml").read_text(
        encoding="utf-8"
    )
    assert "uses: stellar888/repo-doc@v0.5.0" in workflow
    assert "base: origin/${{ github.base_ref }}" in workflow
    assert 'include-agents-doc: "true"' in workflow
    assert 'mock: "true"' in workflow
    assert "OPENAI_API_KEY" not in workflow


def test_init_ci_refuses_to_overwrite_existing_workflow(tmp_path: Path) -> None:
    workflow = tmp_path / ".github" / "workflows" / "repo-doc.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("name: existing\n", encoding="utf-8")

    result = runner.invoke(app, ["init", "--repo-root", str(tmp_path), "--ci"])

    assert result.exit_code == 1
    assert workflow.read_text(encoding="utf-8") == "name: existing\n"


def test_load_diff_prefers_explicit_diff_file(tmp_path: Path) -> None:
    diff_file = tmp_path / "change.diff"
    diff_file.write_text("diff --git a/README.md b/README.md\n+hello\n", encoding="utf-8")

    diff = _load_diff(
        diff_file=diff_file,
        repo_root=tmp_path,
        staged=False,
        base=None,
    )

    assert "+hello" in diff


def test_load_diff_rejects_staged_and_base_together(tmp_path: Path) -> None:
    with pytest.raises(typer.BadParameter):
        _load_diff(
            diff_file=None,
            repo_root=tmp_path,
            staged=True,
            base="main",
        )


def test_load_project_config_from_repo_doc_toml(tmp_path: Path) -> None:
    (tmp_path / "repo-doc.toml").write_text(
        """
allowed_doc_paths = ["docs", "README.md", "guides"]
base_branch = "main"
max_diff_chars = 1234
max_doc_chars = 567
openai_model = "gpt-5-mini"
include_agents_doc = true
""".strip(),
        encoding="utf-8",
    )

    config = load_project_config(tmp_path)
    settings = apply_project_config(Settings(openai_api_key=None), config)

    assert config.base_branch == "main"
    assert settings.allowed_paths == ("docs", "README.md", "guides", "AGENTS.md")
    assert settings.max_diff_chars == 1234
    assert settings.max_doc_chars == 567
    assert settings.include_agents_doc


def test_doctor_can_include_agents_doc(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["doctor", "--repo-root", str(tmp_path), "--include-agents-doc"],
    )

    assert result.exit_code == 0
    assert '"AGENTS.md"' in result.output
    assert '"include_agents_doc": true' in result.output


def test_check_exits_nonzero_when_docs_are_needed(tmp_path: Path) -> None:
    diff_file = tmp_path / "change.diff"
    diff_file.write_text(
        """
diff --git a/src/api.py b/src/api.py
+@app.get("/v1/widgets")
+def list_widgets():
+    return {"items": []}
""".strip(),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["check", "--diff-file", str(diff_file), "--repo-root", str(tmp_path), "--mock"],
    )

    assert result.exit_code == 2
    assert "Documentation updates are needed" in result.output


def test_check_exits_zero_when_no_docs_are_needed(tmp_path: Path) -> None:
    diff_file = tmp_path / "change.diff"
    diff_file.write_text(
        """
diff --git a/src/math.py b/src/math.py
-def add(a, b): return a+b
+def add(left, right): return left + right
""".strip(),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["check", "--diff-file", str(diff_file), "--repo-root", str(tmp_path), "--mock"],
    )

    assert result.exit_code == 0
    assert "No documentation update required" in result.output


def test_check_can_request_agents_doc_update_when_enabled(tmp_path: Path) -> None:
    diff_file = tmp_path / "change.diff"
    diff_file.write_text(
        """
diff --git a/src/repo_doc_agent/cli.py b/src/repo_doc_agent/cli.py
+# Codex coding agent workflow guidance changed.
""".strip(),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "check",
            "--diff-file",
            str(diff_file),
            "--repo-root",
            str(tmp_path),
            "--mock",
            "--include-agents-doc",
        ],
    )

    assert result.exit_code == 2
    assert '"AGENTS.md"' in result.output
    assert "Documentation updates are needed" in result.output


def test_render_markdown_result_includes_preview_sections() -> None:
    result = AgentResult(
        status="ok",
        analysis=ImpactAnalysis(
            needs_documentation_update=True,
            summary="A widgets endpoint was added.",
            candidate_files=["docs/api.md"],
            findings=[
                Finding(
                    category="api_change",
                    evidence="The diff adds /v1/widgets.",
                    confidence=0.91,
                )
            ],
        ),
        proposal=DocumentationProposal(
            action="update",
            summary="Document widgets.",
            edits=[
                {
                    "path": "docs/api.md",
                    "rationale": "The endpoint is externally visible.",
                    "proposed_markdown": "## Widgets\n\nUse `GET /v1/widgets`.",
                    "unified_diff": "--- a/docs/api.md\n+++ b/docs/api.md\n+## Widgets\n",
                }
            ],
        ),
        safety_flags=[],
        prompt_version="test",
        model="mock",
    )

    rendered = _render_markdown_result(result)

    assert "# repo-doc Preview" in rendered
    assert "## Findings" in rendered
    assert "### `docs/api.md`" in rendered
    assert "```diff" in rendered


def test_render_agent_json_result_includes_agent_contract() -> None:
    result = AgentResult(
        status="ok",
        analysis=ImpactAnalysis(
            needs_documentation_update=True,
            summary="A widgets endpoint was added.",
            candidate_files=["docs/api.md"],
            findings=[],
        ),
        proposal=DocumentationProposal(
            action="update",
            summary="Document widgets.",
            edits=[
                {
                    "path": "docs/api.md",
                    "rationale": "The endpoint is externally visible.",
                    "proposed_markdown": "## Widgets\n\nUse `GET /v1/widgets`.",
                }
            ],
        ),
        safety_flags=[],
        prompt_version="test",
        model="mock",
    )

    payload = json.loads(_render_agent_json_result(result))

    assert payload["schema_version"] == 1
    assert payload["next_action"] == "update_documentation"
    assert payload["check_exit_code"] == 2
    assert payload["can_apply"] is True
    assert payload["documentation_files"] == ["docs/api.md"]


def test_analyse_writes_markdown_output(tmp_path: Path) -> None:
    diff_file = tmp_path / "change.diff"
    output_file = tmp_path / "preview.md"
    diff_file.write_text(
        """
diff --git a/src/api.py b/src/api.py
+@app.get("/v1/widgets")
+def list_widgets():
+    return {"items": []}
""".strip(),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "analyse",
            "--diff-file",
            str(diff_file),
            "--repo-root",
            str(tmp_path),
            "--mock",
            "--format",
            "markdown",
            "--output",
            str(output_file),
        ],
    )

    assert result.exit_code == 0
    preview = output_file.read_text(encoding="utf-8")
    assert preview.startswith("# repo-doc Preview")
    assert "### `docs/api.md`" in preview


def test_check_writes_agent_json_output(tmp_path: Path) -> None:
    diff_file = tmp_path / "change.diff"
    output_file = tmp_path / "agent.json"
    diff_file.write_text(
        """
diff --git a/src/math.py b/src/math.py
-def add(a, b): return a+b
+def add(left, right): return left + right
""".strip(),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "check",
            "--diff-file",
            str(diff_file),
            "--repo-root",
            str(tmp_path),
            "--mock",
            "--format",
            "agent-json",
            "--output",
            str(output_file),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert payload["next_action"] == "no_documentation_change"
    assert payload["check_exit_code"] == 0
    assert payload["can_apply"] is False


def test_check_quiet_agent_json_suppresses_status_output(tmp_path: Path) -> None:
    diff_file = tmp_path / "change.diff"
    diff_file.write_text(
        """
diff --git a/src/math.py b/src/math.py
-def add(a, b): return a+b
+def add(left, right): return left + right
""".strip(),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "check",
            "--diff-file",
            str(diff_file),
            "--repo-root",
            str(tmp_path),
            "--mock",
            "--format",
            "agent-json",
            "--quiet",
        ],
    )

    assert result.exit_code == 0
    assert result.output.lstrip().startswith("{")
    assert "repo-doc check" not in result.output
    assert "No documentation update required" not in result.output
    payload = json.loads(result.output)
    assert payload["next_action"] == "no_documentation_change"

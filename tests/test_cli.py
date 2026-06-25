from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from repo_doc_agent.cli import _load_diff, _render_markdown_result, app
from repo_doc_agent.config import Settings, apply_project_config, load_project_config
from repo_doc_agent.schemas import AgentResult, DocumentationProposal, Finding, ImpactAnalysis

runner = CliRunner()


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

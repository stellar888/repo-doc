from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from repo_doc_agent.cli import _load_diff, app
from repo_doc_agent.config import Settings, apply_project_config, load_project_config

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
""".strip(),
        encoding="utf-8",
    )

    config = load_project_config(tmp_path)
    settings = apply_project_config(Settings(openai_api_key=None), config)

    assert config.base_branch == "main"
    assert settings.allowed_paths == ("docs", "README.md", "guides")
    assert settings.max_diff_chars == 1234
    assert settings.max_doc_chars == 567


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

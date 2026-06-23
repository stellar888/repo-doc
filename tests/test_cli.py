from pathlib import Path

import pytest
import typer

from repo_doc_agent.cli import _load_diff


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

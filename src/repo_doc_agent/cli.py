from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.syntax import Syntax

from .config import Settings
from .documentation import apply_documentation_proposal
from .graph import run_agent
from .model import MockStructuredModel, OpenAIStructuredModel

app = typer.Typer(no_args_is_help=True)
console = Console()


def _run_git(args: list[str], *, repo_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise typer.BadParameter("git is required when --diff-file is not supplied") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        raise typer.BadParameter(f"git {' '.join(args)} failed: {detail}") from exc
    return completed.stdout


def _load_diff(
    *,
    diff_file: Path | None,
    repo_root: Path,
    staged: bool,
    base: str | None,
) -> str:
    if diff_file:
        return diff_file.read_text(encoding="utf-8")

    if base and staged:
        raise typer.BadParameter("Use either --base or --staged, not both")

    resolved_root = repo_root.resolve()
    if base:
        merge_base = _run_git(["merge-base", base, "HEAD"], repo_root=resolved_root).strip()
        return _run_git(["diff", merge_base, "HEAD"], repo_root=resolved_root)

    if staged:
        return _run_git(["diff", "--cached"], repo_root=resolved_root)

    staged_diff = _run_git(["diff", "--cached"], repo_root=resolved_root)
    working_diff = _run_git(["diff"], repo_root=resolved_root)
    return "\n".join(part for part in (staged_diff, working_diff) if part.strip())


@app.command()
def analyse(
    diff_file: Annotated[
        Path | None,
        typer.Option(
            exists=True,
            readable=True,
            help="Optional saved diff. If omitted, repo-doc reads Git changes from --repo-root.",
        ),
    ] = None,
    repo_root: Annotated[
        Path,
        typer.Option(
            exists=True,
            file_okay=False,
            help="Repository whose docs may be read. Defaults to the current directory.",
        ),
    ] = Path("."),
    allowed_doc_path: Annotated[
        list[str] | None,
        typer.Option(
            "--allowed-doc-path",
            help="Allowed doc path. Repeat to override ALLOWED_DOC_DIRS.",
        ),
    ] = None,
    staged: Annotated[
        bool,
        typer.Option(help="Analyse only staged changes using git diff --cached."),
    ] = False,
    base: Annotated[
        str | None,
        typer.Option(help="Analyse committed branch changes since the merge-base with this ref."),
    ] = None,
    mock: Annotated[bool, typer.Option(help="Use deterministic local model.")] = False,
    apply: Annotated[
        bool,
        typer.Option(
            "--apply",
            help="Write proposed documentation changes when the result is safe to apply.",
        ),
    ] = False,
    output: Annotated[Path | None, typer.Option(help="Optional JSON output file.")] = None,
) -> None:
    """Analyse Git changes and produce a bounded documentation proposal."""
    settings = Settings()
    settings.repository_root = str(repo_root.resolve())
    if allowed_doc_path:
        settings.allowed_doc_dirs = ",".join(allowed_doc_path)

    diff = _load_diff(
        diff_file=diff_file,
        repo_root=repo_root,
        staged=staged,
        base=base,
    )
    if not diff.strip():
        console.print("[yellow]No Git diff found to analyse.[/yellow]")
        raise typer.Exit(code=1)

    model = MockStructuredModel() if mock else OpenAIStructuredModel(settings)
    result = run_agent(
        diff=diff,
        settings=settings,
        model=model,
    )
    rendered = result.model_dump_json(indent=2)
    console.print(Syntax(rendered, "json", word_wrap=True))

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")

    if apply:
        if result.status != "ok" or result.proposal.action != "update":
            console.print(
                "[yellow]Documentation changes were not applied because the result is not "
                "a safe update proposal.[/yellow]"
            )
            raise typer.Exit(code=1)

        applied_paths = apply_documentation_proposal(
            proposal=result.proposal,
            repository_root=repo_root.resolve(),
            allowed_paths=settings.allowed_paths,
        )
        if not applied_paths:
            console.print(
                "[yellow]No documentation files changed; proposed content already exists.[/yellow]"
            )
            return

        for path in applied_paths:
            console.print(f"[green]Applied documentation update:[/green] {path}")


@app.command()
def doctor() -> None:
    """Validate local configuration without calling a model."""
    settings = Settings()
    checks = {
        "python_package": "ok",
        "allowed_paths": settings.allowed_paths,
        "max_diff_chars": settings.max_diff_chars,
        "max_doc_chars": settings.max_doc_chars,
        "repository_root": settings.repository_root,
        "openai_key_present": bool(settings.openai_api_key),
        "dry_run": settings.agent_dry_run,
    }
    console.print_json(json.dumps(checks))


if __name__ == "__main__":
    app()

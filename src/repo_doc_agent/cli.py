from __future__ import annotations

import json
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.syntax import Syntax

from .config import ProjectConfig, Settings, apply_project_config, load_project_config
from .documentation import apply_documentation_proposal
from .graph import run_agent
from .model import MockStructuredModel, OpenAIStructuredModel
from .schemas import AgentResult

app = typer.Typer(no_args_is_help=True)
console = Console()
log_console = Console(stderr=True)

BANNER = r"""
                 __
  ________ ____  / /___        ____/ /___  _____
 / ___/ _ `/ _ \/ / __ \______/ __  / __ \/ ___/
/ /  /  __/  __/ / /_/ /_____/ /_/ / /_/ / /__
/_/   \___/\___/_/ .___/      \__,_/\____/\___/
                 /_/
""".strip("\n")


def _print_banner(command: str) -> None:
    log_console.print(f"[cyan]{BANNER}[/cyan]")
    log_console.print(f"[bold]repo-doc[/bold] {command}\n")


@contextmanager
def _step(message: str) -> Iterator[None]:
    with log_console.status(f"[cyan]{message}[/cyan]", spinner="dots"):
        yield
    log_console.print(f"[green]OK[/green] {message}")


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


def _settings_from_inputs(
    *,
    repo_root: Path,
    config_file: Path | None,
    allowed_doc_path: list[str] | None,
) -> tuple[Settings, ProjectConfig]:
    resolved_root = repo_root.resolve()
    project_config = load_project_config(resolved_root, config_file)
    settings = apply_project_config(Settings(), project_config)
    settings.repository_root = str(resolved_root)

    if allowed_doc_path:
        settings.allowed_doc_dirs = ",".join(allowed_doc_path)

    return settings, project_config


def _run_analysis(
    *,
    settings: Settings,
    diff_file: Path | None,
    repo_root: Path,
    staged: bool,
    base: str | None,
    mock: bool,
) -> AgentResult:
    with _step("Reading Git changes"):
        diff = _load_diff(
            diff_file=diff_file,
            repo_root=repo_root,
            staged=staged,
            base=base,
        )
    if not diff.strip():
        log_console.print("[yellow]No Git diff found to analyse.[/yellow]")
        raise typer.Exit(code=1)

    with _step("Running documentation agent"):
        model = MockStructuredModel() if mock else OpenAIStructuredModel(settings)
        return run_agent(
            diff=diff,
            settings=settings,
            model=model,
        )


def _print_and_write_result(result: AgentResult, output: Path | None) -> None:
    rendered = result.model_dump_json(indent=2)
    console.print(Syntax(rendered, "json", word_wrap=True))

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")


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
    config_file: Annotated[
        Path | None,
        typer.Option(
            exists=True,
            dir_okay=False,
            readable=True,
            help="Optional repo-doc.toml path. Defaults to --repo-root/repo-doc.toml.",
        ),
    ] = None,
    allowed_doc_path: Annotated[
        list[str] | None,
        typer.Option(
            "--allowed-doc-path",
            help="Allowed doc path. Repeat to override repo-doc.toml and ALLOWED_DOC_DIRS.",
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
    _print_banner("analyse")
    with _step("Loading configuration"):
        settings, _project_config = _settings_from_inputs(
            repo_root=repo_root,
            config_file=config_file,
            allowed_doc_path=allowed_doc_path,
        )
    result = _run_analysis(
        settings=settings,
        diff_file=diff_file,
        repo_root=repo_root,
        staged=staged,
        base=base,
        mock=mock,
    )
    _print_and_write_result(result, output)

    if apply:
        if result.status != "ok" or result.proposal.action != "update":
            log_console.print(
                "[yellow]Documentation changes were not applied because the result is not "
                "a safe update proposal.[/yellow]"
            )
            raise typer.Exit(code=1)

        with _step("Applying documentation changes"):
            applied_paths = apply_documentation_proposal(
                proposal=result.proposal,
                repository_root=repo_root.resolve(),
                allowed_paths=settings.allowed_paths,
        )
        if not applied_paths:
            log_console.print(
                "[yellow]No documentation files changed; proposed content already exists.[/yellow]"
            )
            return

        for path in applied_paths:
            log_console.print(f"[green]Applied documentation update:[/green] {path}")


@app.command()
def check(
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
    config_file: Annotated[
        Path | None,
        typer.Option(
            exists=True,
            dir_okay=False,
            readable=True,
            help="Optional repo-doc.toml path. Defaults to --repo-root/repo-doc.toml.",
        ),
    ] = None,
    allowed_doc_path: Annotated[
        list[str] | None,
        typer.Option(
            "--allowed-doc-path",
            help="Allowed doc path. Repeat to override repo-doc.toml and ALLOWED_DOC_DIRS.",
        ),
    ] = None,
    staged: Annotated[
        bool,
        typer.Option(help="Check only staged changes using git diff --cached."),
    ] = False,
    base: Annotated[
        str | None,
        typer.Option(help="Check committed branch changes since the merge-base with this ref."),
    ] = None,
    mock: Annotated[bool, typer.Option(help="Use deterministic local model.")] = False,
    output: Annotated[Path | None, typer.Option(help="Optional JSON output file.")] = None,
) -> None:
    """CI-friendly documentation gate for Git changes."""
    _print_banner("check")
    with _step("Loading configuration"):
        settings, project_config = _settings_from_inputs(
            repo_root=repo_root,
            config_file=config_file,
            allowed_doc_path=allowed_doc_path,
        )
    effective_base = base or (None if diff_file or staged else project_config.base_branch)
    result = _run_analysis(
        settings=settings,
        diff_file=diff_file,
        repo_root=repo_root,
        staged=staged,
        base=effective_base,
        mock=mock,
    )
    _print_and_write_result(result, output)

    if result.status == "ok" and result.proposal.action == "no_change":
        log_console.print("[green]No documentation update required.[/green]")
        return

    if result.status == "ok" and result.proposal.action == "update":
        log_console.print("[red]Documentation updates are needed.[/red]")
        raise typer.Exit(code=2)

    if result.status == "human_review":
        log_console.print("[yellow]Documentation check requires human review.[/yellow]")
        raise typer.Exit(code=3)

    log_console.print("[red]Documentation check was blocked by a safety gate.[/red]")
    raise typer.Exit(code=4)


@app.command()
def doctor(
    repo_root: Annotated[
        Path,
        typer.Option(
            exists=True,
            file_okay=False,
            help="Repository root used for repo-doc.toml discovery.",
        ),
    ] = Path("."),
    config_file: Annotated[
        Path | None,
        typer.Option(
            exists=True,
            dir_okay=False,
            readable=True,
            help="Optional repo-doc.toml path. Defaults to --repo-root/repo-doc.toml.",
        ),
    ] = None,
) -> None:
    """Validate local configuration without calling a model."""
    _print_banner("doctor")
    with _step("Loading configuration"):
        settings, project_config = _settings_from_inputs(
            repo_root=repo_root,
            config_file=config_file,
            allowed_doc_path=None,
        )
    checks = {
        "python_package": "ok",
        "allowed_paths": settings.allowed_paths,
        "base_branch": project_config.base_branch,
        "max_diff_chars": settings.max_diff_chars,
        "max_doc_chars": settings.max_doc_chars,
        "repository_root": settings.repository_root,
        "openai_key_present": bool(settings.openai_api_key),
        "dry_run": settings.agent_dry_run,
    }
    console.print_json(json.dumps(checks))


if __name__ == "__main__":
    app()

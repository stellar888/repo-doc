from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Literal

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.syntax import Syntax

from . import __version__
from .config import ProjectConfig, Settings, apply_project_config, load_project_config
from .contract import render_agent_json_result as _render_agent_json_result
from .documentation import apply_documentation_proposal
from .graph import run_agent
from .model import MockStructuredModel, OpenAIStructuredModel
from .schemas import AgentResult

OutputFormat = Literal["json", "agent-json", "markdown", "rich"]

app = typer.Typer(no_args_is_help=True, invoke_without_command=True)
console = Console()
log_console = Console(stderr=True)

BANNER = r"""
                               __
   ________  ____  ____   ___ / /___  _____
  / ___/ _ \/ __ \/ __ \ / __  / __ \/ ___/
 / /  /  __/ /_/ / /_/ /  /_/ /_/ / / /__
/_/   \___/  ___/\____(_)_____\____/\___/
          /_/
""".strip("\n")


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Show the installed repo-doc version and exit.",
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Controlled documentation-impact agent."""
    if version:
        console.print(f"repo-doc {__version__}")
        raise typer.Exit()


def _print_banner(command: str, *, quiet: bool) -> None:
    if quiet:
        return
    log_console.print(f"[cyan]{BANNER}[/cyan]")
    log_console.print(f"[bold]repo-doc[/bold] {command}\n")


@contextmanager
def _step(message: str, *, quiet: bool) -> Iterator[None]:
    if quiet:
        yield
        return
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
    include_agents_doc: bool,
) -> tuple[Settings, ProjectConfig]:
    resolved_root = repo_root.resolve()
    project_config = load_project_config(resolved_root, config_file)
    settings = apply_project_config(Settings(), project_config)
    settings.repository_root = str(resolved_root)

    if allowed_doc_path:
        settings.allowed_doc_dirs = ",".join(allowed_doc_path)
    if include_agents_doc:
        settings.include_agents_doc = True

    return settings, project_config


def _detect_allowed_doc_paths(repo_root: Path) -> list[str]:
    candidates = ["docs", "documentation", "guides", "README.md"]
    detected = []
    for candidate in candidates:
        path = repo_root / candidate
        if path.exists():
            detected.append(candidate)
    return detected or ["docs", "README.md"]


def _toml_array(values: list[str]) -> str:
    return "[" + ", ".join(json.dumps(value) for value in values) + "]"


def _render_project_config(
    *,
    allowed_doc_paths: list[str],
    include_agents_doc: bool,
    base_branch: str,
) -> str:
    defaults = Settings(openai_api_key=None)
    lines = [
        f"allowed_doc_paths = {_toml_array(allowed_doc_paths)}",
        f"include_agents_doc = {str(include_agents_doc).lower()}",
        f"base_branch = {json.dumps(base_branch)}",
        f"max_diff_chars = {defaults.max_diff_chars}",
        f"max_doc_chars = {defaults.max_doc_chars}",
        f"openai_model = {json.dumps(defaults.openai_model)}",
        "",
    ]
    return "\n".join(lines)


def _run_analysis(
    *,
    settings: Settings,
    diff_file: Path | None,
    repo_root: Path,
    staged: bool,
    base: str | None,
    mock: bool,
    quiet: bool,
) -> AgentResult:
    with _step("Reading Git changes", quiet=quiet):
        diff = _load_diff(
            diff_file=diff_file,
            repo_root=repo_root,
            staged=staged,
            base=base,
        )
    if not diff.strip():
        if not quiet:
            log_console.print("[yellow]No Git diff found to analyse.[/yellow]")
        raise typer.Exit(code=1)

    with _step("Running documentation agent", quiet=quiet):
        model = MockStructuredModel() if mock else OpenAIStructuredModel(settings)
        return run_agent(
            diff=diff,
            settings=settings,
            model=model,
        )


def _render_markdown_result(result: AgentResult) -> str:
    lines = [
        "# repo-doc Preview",
        "",
        f"- **Status:** `{result.status}`",
        f"- **Action:** `{result.proposal.action}`",
        f"- **Model:** `{result.model}`",
        f"- **Prompt version:** `{result.prompt_version}`",
        "",
        "## Summary",
        "",
        result.proposal.summary or result.analysis.summary,
        "",
        "## Findings",
        "",
    ]

    if result.analysis.findings:
        lines.extend([
            "| Category | Confidence | Evidence |",
            "|---|---:|---|",
        ])
        for finding in result.analysis.findings:
            evidence = finding.evidence.replace("|", "\\|").replace("\n", " ")
            lines.append(f"| `{finding.category}` | {finding.confidence:.2f} | {evidence} |")
    else:
        lines.append("No findings were reported.")

    lines.extend(["", "## Candidate Files", ""])
    if result.analysis.candidate_files:
        lines.extend(f"- `{path}`" for path in result.analysis.candidate_files)
    else:
        lines.append("No candidate documentation files were selected.")

    lines.extend(["", "## Proposed Edits", ""])
    if result.proposal.edits:
        for edit in result.proposal.edits:
            lines.extend([
                f"### `{edit.path}`",
                "",
                f"**Operation:** `{edit.operation}`",
                "",
            ])
            if edit.target_heading:
                lines.extend([f"**Target heading:** `{edit.target_heading}`", ""])
            lines.extend(
                [
                    f"**Rationale:** {edit.rationale}",
                    "",
                    "```markdown",
                    edit.proposed_markdown.rstrip(),
                    "```",
                ]
            )
            if edit.unified_diff:
                lines.extend(["", "```diff", edit.unified_diff.rstrip(), "```"])
            lines.append("")
    else:
        lines.append("No documentation edits were proposed.")

    if result.proposal.reviewer_notes:
        lines.extend(["", "## Reviewer Notes", ""])
        lines.extend(f"- {note}" for note in result.proposal.reviewer_notes)

    if result.safety_flags:
        lines.extend(["", "## Safety Flags", ""])
        lines.extend(f"- `{flag}`" for flag in result.safety_flags)

    if result.analysis.uncertainty:
        lines.extend(["", "## Uncertainty", "", result.analysis.uncertainty])

    return "\n".join(lines).rstrip() + "\n"


def _render_result(result: AgentResult, output_format: OutputFormat) -> str:
    if output_format == "json":
        return result.model_dump_json(indent=2) + "\n"
    if output_format == "agent-json":
        return _render_agent_json_result(result)
    return _render_markdown_result(result)


def _print_and_write_result(
    result: AgentResult,
    output: Path | None,
    output_format: OutputFormat,
) -> None:
    rendered = _render_result(result, output_format)
    if output_format == "json":
        console.print(Syntax(rendered.rstrip(), "json", word_wrap=True))
    elif output_format == "agent-json":
        sys.stdout.write(rendered)
    elif output_format == "rich":
        console.print(Markdown(rendered))
    else:
        sys.stdout.write(rendered)

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")


@app.command()
def init(
    repo_root: Annotated[
        Path,
        typer.Option(
            exists=True,
            file_okay=False,
            help="Repository root where repo-doc.toml should be created.",
        ),
    ] = Path("."),
    config_file: Annotated[
        Path | None,
        typer.Option(
            dir_okay=False,
            help="Optional config path. Defaults to --repo-root/repo-doc.toml.",
        ),
    ] = None,
    allowed_doc_path: Annotated[
        list[str] | None,
        typer.Option(
            "--allowed-doc-path",
            help="Allowed doc path. Repeat to override automatic detection.",
        ),
    ] = None,
    include_agents_doc: Annotated[
        bool,
        typer.Option(
            "--include-agents-doc",
            help="Allow repo-doc to read, create, and update AGENTS.md.",
        ),
    ] = False,
    base_branch: Annotated[
        str,
        typer.Option(help="Default base branch ref for check when --base is omitted."),
    ] = "main",
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite an existing repo-doc.toml."),
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", help="Suppress banners and status messages."),
    ] = False,
) -> None:
    """Create a starter repo-doc.toml for this repository."""
    _print_banner("init", quiet=quiet)
    resolved_root = repo_root.resolve()
    target = config_file or resolved_root / "repo-doc.toml"

    if target.exists() and not force:
        if not quiet:
            log_console.print(
                f"[yellow]{target} already exists. Use --force to overwrite it.[/yellow]"
            )
        raise typer.Exit(code=1)

    allowed_paths = allowed_doc_path or _detect_allowed_doc_paths(resolved_root)
    rendered = _render_project_config(
        allowed_doc_paths=allowed_paths,
        include_agents_doc=include_agents_doc,
        base_branch=base_branch,
    )

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered, encoding="utf-8")

    if not quiet:
        log_console.print(f"[green]Created repo-doc configuration:[/green] {target}")
        console.print(Syntax(rendered.rstrip(), "toml", word_wrap=True))
    else:
        sys.stdout.write(rendered)


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
    include_agents_doc: Annotated[
        bool,
        typer.Option(
            "--include-agents-doc",
            help="Allow repo-doc to read, create, and update AGENTS.md.",
        ),
    ] = False,
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
    output_format: Annotated[
        OutputFormat,
        typer.Option(
            "--format",
            help="Output format: json, agent-json, markdown, or rich terminal markdown.",
        ),
    ] = "json",
    output: Annotated[Path | None, typer.Option(help="Optional output file.")] = None,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", help="Suppress banners and status messages."),
    ] = False,
) -> None:
    """Analyse Git changes and produce a bounded documentation proposal."""
    _print_banner("analyse", quiet=quiet)
    with _step("Loading configuration", quiet=quiet):
        settings, _project_config = _settings_from_inputs(
            repo_root=repo_root,
            config_file=config_file,
            allowed_doc_path=allowed_doc_path,
            include_agents_doc=include_agents_doc,
        )
    result = _run_analysis(
        settings=settings,
        diff_file=diff_file,
        repo_root=repo_root,
        staged=staged,
        base=base,
        mock=mock,
        quiet=quiet,
    )
    _print_and_write_result(result, output, output_format)

    if apply:
        if result.status != "ok" or result.proposal.action != "update":
            if not quiet:
                log_console.print(
                    "[yellow]Documentation changes were not applied because the result is not "
                    "a safe update proposal.[/yellow]"
                )
            raise typer.Exit(code=1)

        with _step("Applying documentation changes", quiet=quiet):
            applied_paths = apply_documentation_proposal(
                proposal=result.proposal,
                repository_root=repo_root.resolve(),
                allowed_paths=settings.allowed_paths,
            )
        if not applied_paths:
            if not quiet:
                log_console.print(
                    "[yellow]No documentation files changed; proposed content already "
                    "exists.[/yellow]"
                )
            return

        if not quiet:
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
    include_agents_doc: Annotated[
        bool,
        typer.Option(
            "--include-agents-doc",
            help="Allow repo-doc to read, create, and update AGENTS.md.",
        ),
    ] = False,
    staged: Annotated[
        bool,
        typer.Option(help="Check only staged changes using git diff --cached."),
    ] = False,
    base: Annotated[
        str | None,
        typer.Option(help="Check committed branch changes since the merge-base with this ref."),
    ] = None,
    mock: Annotated[bool, typer.Option(help="Use deterministic local model.")] = False,
    output_format: Annotated[
        OutputFormat,
        typer.Option(
            "--format",
            help="Output format: json, agent-json, markdown, or rich terminal markdown.",
        ),
    ] = "json",
    output: Annotated[Path | None, typer.Option(help="Optional output file.")] = None,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", help="Suppress banners and status messages."),
    ] = False,
) -> None:
    """CI-friendly documentation gate for Git changes."""
    _print_banner("check", quiet=quiet)
    with _step("Loading configuration", quiet=quiet):
        settings, project_config = _settings_from_inputs(
            repo_root=repo_root,
            config_file=config_file,
            allowed_doc_path=allowed_doc_path,
            include_agents_doc=include_agents_doc,
        )
    effective_base = base or (None if diff_file or staged else project_config.base_branch)
    result = _run_analysis(
        settings=settings,
        diff_file=diff_file,
        repo_root=repo_root,
        staged=staged,
        base=effective_base,
        mock=mock,
        quiet=quiet,
    )
    _print_and_write_result(result, output, output_format)

    if result.status == "ok" and result.proposal.action == "no_change":
        if not quiet:
            log_console.print("[green]No documentation update required.[/green]")
        return

    if result.status == "ok" and result.proposal.action == "update":
        if not quiet:
            log_console.print("[red]Documentation updates are needed.[/red]")
        raise typer.Exit(code=2)

    if result.status == "human_review":
        if not quiet:
            log_console.print("[yellow]Documentation check requires human review.[/yellow]")
        raise typer.Exit(code=3)

    if not quiet:
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
    include_agents_doc: Annotated[
        bool,
        typer.Option(
            "--include-agents-doc",
            help="Allow repo-doc to read, create, and update AGENTS.md.",
        ),
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", help="Suppress banners and status messages."),
    ] = False,
) -> None:
    """Validate local configuration without calling a model."""
    _print_banner("doctor", quiet=quiet)
    with _step("Loading configuration", quiet=quiet):
        settings, project_config = _settings_from_inputs(
            repo_root=repo_root,
            config_file=config_file,
            allowed_doc_path=None,
            include_agents_doc=include_agents_doc,
        )
    checks = {
        "python_package": "ok",
        "allowed_paths": settings.allowed_paths,
        "base_branch": project_config.base_branch,
        "max_diff_chars": settings.max_diff_chars,
        "max_doc_chars": settings.max_doc_chars,
        "repository_root": settings.repository_root,
        "include_agents_doc": settings.include_agents_doc,
        "openai_key_present": bool(settings.openai_api_key),
        "dry_run": settings.agent_dry_run,
    }
    console.print_json(json.dumps(checks))


if __name__ == "__main__":
    app()

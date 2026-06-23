from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.syntax import Syntax

from .config import Settings
from .graph import run_agent
from .model import MockStructuredModel, OpenAIStructuredModel

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command()
def analyse(
    diff_file: Annotated[Path, typer.Option(exists=True, readable=True)],
    mock: Annotated[bool, typer.Option(help="Use deterministic local model.")] = False,
    output: Annotated[Path | None, typer.Option(help="Optional JSON output file.")] = None,
) -> None:
    """Analyse a Git diff and produce a bounded documentation proposal."""
    settings = Settings()
    model = MockStructuredModel() if mock else OpenAIStructuredModel(settings)
    result = run_agent(
        diff=diff_file.read_text(encoding="utf-8"),
        settings=settings,
        model=model,
    )
    rendered = result.model_dump_json(indent=2)
    console.print(Syntax(rendered, "json", word_wrap=True))

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")


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

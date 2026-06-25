# Agent Instructions

This repository contains `repo-doc`, a cautious documentation-impact agent. Treat it as a safety
tool first and an automation tool second.

## Working In This Repo

- Keep changes scoped to the documentation agent, tests, docs, and examples relevant to the task.
- Preserve the trust boundary: diffs, repository text, and model output are untrusted.
- Do not add model tool access, shell execution, GitHub writes, commits, merges, or deployment
  behavior to the model path.
- Prefer deterministic Python validation over prompt-only enforcement.
- Keep new CLI behavior usable by both humans and coding agents.
- Update docs and tests with behavior changes.

## Common Commands

Use the local virtualenv when available:

```bash
.venv/bin/python -m pytest
.venv/bin/ruff check .
.venv/bin/python -m mypy
```

For coverage:

```bash
.venv/bin/python -m pytest --cov=repo_doc_agent --cov-report=term-missing
```

For package/reinstall validation:

```bash
.venv/bin/python -m build
.venv/bin/python -m pip install --force-reinstall --no-deps dist/*.whl
.venv/bin/repo-doc --version
.venv/bin/repo-doc --help
```

For deterministic local repo-doc runs:

```bash
.venv/bin/repo-doc analyse --diff-file examples/api-change.diff --mock
.venv/bin/repo-doc check --diff-file examples/no-doc-change.diff --mock --format agent-json --quiet
```

For Promptfoo black-box contract checks:

```bash
PROMPTFOO_PYTHON=.venv/bin/python npx --yes promptfoo@latest eval -c evals/promptfooconfig.yaml
```

Avoid live OpenAI calls unless the user explicitly wants model-backed behavior verified.

## Important Files

- `src/repo_doc_agent/cli.py`: Typer CLI, output formats, config initialization.
- `src/repo_doc_agent/graph.py`: LangGraph workflow and safety routing.
- `src/repo_doc_agent/documentation.py`: allowed doc reads, candidate discovery, diffs, apply logic.
- `src/repo_doc_agent/security.py`: prompt-injection, secret, and path validation.
- `src/repo_doc_agent/prompts.py`: versioned system and task prompts.
- `src/repo_doc_agent/schemas.py`: structured model and result contracts.
- `tests/`: regression tests for CLI, graph, Promptfoo provider, and security invariants.
- `evals/`: Promptfoo black-box scenarios for the `agent-json` contract.

## Safety Expectations

- Secret-like diff input must block before model execution.
- Existing documentation containing secret-like content must be redacted before model execution.
- Truncated documentation context must require human review before apply.
- Proposed edit paths must stay inside configured documentation paths.
- Invalid edit operations must block the run.
- `--apply` must only write safe `status=ok` update proposals.

## Agentic Flow Contract

Use `agent-json` when another agent needs to consume repo-doc output:

```bash
repo-doc check --format agent-json --quiet --output repo-doc-agent.json
```

Branch on:

- `next_action=no_documentation_change`: continue.
- `next_action=update_documentation`: update docs or run a safe apply path.
- `next_action=request_human_review`: stop and ask a human.
- `next_action=stop_for_safety_review`: stop; do not apply changes.

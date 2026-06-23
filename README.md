# repo-doc

A deliberately constrained AI agent that checks whether code changes need documentation updates.

The agent accepts a Git diff, determines whether documentation needs to change, safely reads
relevant existing docs, and returns a reviewable Markdown proposal with a generated unified diff.
It uses LangGraph for stateful orchestration, LangChain's OpenAI integration for structured model
outputs, deterministic Python safety gates, Promptfoo for black-box evaluations, Pytest for unit
tests, and GitHub Actions for CI.

## Why this architecture?

This is not an unrestricted autonomous coding bot. The outer workflow is deterministic:

1. Validate and truncate the incoming diff.
2. Detect suspicious prompt-injection-like content.
3. Ask the model for structured impact analysis.
4. Read only candidate documentation files inside approved paths.
5. Ask the model for a bounded documentation proposal using that context.
6. Generate unified diffs from trusted application code.
7. Apply deterministic path, schema, and content checks.
8. Return a reviewable result by default, or write documentation only when `--apply` is used.

The model can recommend changes but cannot execute shell commands, read secrets, write outside
approved documentation paths, commit, merge, or deploy code.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Run safely without an API key against the included demo diff:

```bash
repo-doc analyse --diff-file examples/api-change.diff --mock
```

Run with OpenAI:

```bash
export OPENAI_API_KEY="..."
repo-doc analyse --diff-file examples/api-change.diff
```

## Use on your own repo

Install `repo-doc`, then run it from the repository you are changing:

```bash
cd /path/to/your/project
repo-doc analyse
```

By default, this analyses both staged and unstaged changes by combining `git diff --cached` and
`git diff`. That is the most useful mode while you are developing on a branch and want to ask:
"Should I update docs before I commit?"

Common modes:

```bash
# Analyse all current uncommitted changes in this repo
repo-doc analyse

# Analyse only staged changes, useful in a pre-commit flow
repo-doc analyse --staged

# Analyse all committed changes on this branch compared with main
repo-doc analyse --base main

# Analyse a saved diff, useful in CI or external tooling
repo-doc analyse --diff-file /tmp/change.diff

# Run against another repo without cd-ing into it
repo-doc analyse --repo-root /path/to/your/project
```

By default, `repo-doc` is review-only. To write safe documentation proposals into the allowed doc
files, opt in explicitly:

```bash
repo-doc analyse --apply
```

`--apply` only writes when `status` is `ok` and `proposal.action` is `update`. It refuses to write
for `human_review`, `blocked`, and `no_change` results, and it still only writes inside allowed doc
paths.

Limit the docs it may read or propose edits for:

```bash
repo-doc analyse \
  --allowed-doc-path docs \
  --allowed-doc-path README.md \
  --allowed-doc-path guides
```

The output is JSON. The important fields are:

- `status`: `ok`, `human_review`, or `blocked`.
- `analysis`: the model's structured explanation of documentation impact.
- `proposal.edits`: proposed Markdown changes.
- `proposal.edits[].unified_diff`: a patch-style review artifact.

The tool never commits, merges, deploys, or opens pull requests automatically. Without `--apply`,
it only proposes changes and generates reviewable diffs.

Useful settings:

- `OPENAI_MODEL`: model used by LangChain's OpenAI chat client.
- `ALLOWED_DOC_DIRS`: comma-separated documentation paths the agent may read or propose edits for.
- `REPOSITORY_ROOT`: root used when reading existing documentation when `--repo-root` is omitted.
- `MAX_DIFF_CHARS` and `MAX_DOC_CHARS`: input caps before model calls.

Run tests:

```bash
pytest
ruff check .
mypy
```

Run Promptfoo evaluations:

```bash
npx promptfoo@latest eval -c evals/promptfooconfig.yaml \
  -o artifacts/promptfoo.json \
  -o artifacts/promptfoo.html
```

Promptfoo invokes the application through a Python provider, meaning it evaluates the complete
graph rather than merely evaluating an isolated prompt.

## Production improvements

- Replace model-selected document paths with repository-aware search or embeddings.
- Use a GitHub App instead of a broadly scoped personal token.
- Add a model gateway, tracing, cost budgets, and audit storage.
- Add human-labelled evaluation cases from production incidents.
- Execute documentation builds in an isolated runner.
- Create pull requests through a narrow tool service rather than giving the model GitHub access.
- Add OIDC only when a workflow actually needs cloud access.

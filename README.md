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

For CI or pre-push checks, use `check` instead of `analyse`:

```bash
repo-doc check --base main
```

`check` exits with:

- `0` when no documentation update is required.
- `2` when documentation updates are needed.
- `3` when human review is required.
- `4` when a deterministic safety gate blocks the run.

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

Or commit a `repo-doc.toml` to each repository that uses the tool:

```toml
allowed_doc_paths = ["docs", "README.md", "guides"]
base_branch = "main"
max_diff_chars = 40000
max_doc_chars = 12000
openai_model = "gpt-5-mini"
```

There is a copyable starter at `repo-doc.example.toml`.

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

## GitHub Actions check

```yaml
name: repo-doc

on:
  pull_request:

permissions:
  contents: read

jobs:
  docs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install repo-doc
      - run: repo-doc check --base origin/main
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

Use mock mode for deterministic CI demos that do not need an API key:

```bash
repo-doc check --base origin/main --mock
```

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

Repository-local configuration (repo-doc.toml)

You can commit a repo-local configuration file named repo-doc.toml at the root of a repository to provide repository-specific defaults. The tool will also accept an explicit path via --config-file.

Supported keys (top-level table or nested under [tool."repo-doc"]) include:

- allowed_doc_paths: array of strings. Paths or directories the agent may read or propose edits for (e.g. ["docs", "README.md"]).
- base_branch: string. A default branch ref used by CI-oriented flows when no --base is provided.
- max_diff_chars: integer. Maximum diff input size passed to the agent.
- max_doc_chars: integer. Maximum document size the agent will read.
- openai_model: string. Optional model override for the repo.

Example repo-doc.toml

```toml
allowed_doc_paths = ["docs", "README.md", "guides"]
base_branch = "main"
max_diff_chars = 40000
max_doc_chars = 12000
openai_model = "gpt-5-mini"
```

Discovery and precedence

- By default repo-doc.toml is read from the repository root (REPO_ROOT/repo-doc.toml). Use --config-file to point at a different file.
- The TOML may be provided either as a top-level table or nested under the conventional tooling table: [tool."repo-doc"].
- Precedence: explicit CLI flags take priority. In particular, repeating --allowed-doc-path on the CLI overrides values from repo-doc.toml and the ALLOWED_DOC_DIRS environment variable. Settings that are not provided on the CLI fall back to repo-doc.toml and then to built-in defaults / environment variables.

CI-friendly check command

Use repo-doc check when you want a CI gate that returns deterministic exit codes instead of producing a reviewable JSON payload.

- Use-case: run in a GitHub Actions job, pre-push hook, or other CI to fail the job when documentation updates are required.

Exit codes

- 0 — no documentation update is required.
- 2 — documentation updates are needed.
- 3 — human review is required.
- 4 — a deterministic safety gate blocked the run.

Basic usage examples

```bash
# Run the CI-style check against the current repo
repo-doc check --base origin/main

# Use mock mode for deterministic CI demos (no API key required)
repo-doc check --base origin/main --mock

# Specify a repo-local config file explicitly
repo-doc check --config-file /path/to/repo-doc.toml --base origin/main
```

Base-branch resolution for check

When computing which committed changes to analyse the command determines an "effective base" using the following rule:

- If you pass --base explicitly, that value is used.
- If you provided a saved diff with --diff-file or asked the command to check staged changes (--staged), the command does not fall back to repo-doc.toml's base_branch (it treats the base as None and analyses the provided diff or staged changes directly).
- Otherwise, when neither --diff-file nor --staged were used and no --base was given, check will use base_branch from repo-doc.toml if present.

doctor command

The doctor command validates local configuration without calling a model. It now accepts --config-file for repo-doc.toml discovery and reports the resolved configuration values (for example the base_branch and allowed paths) so you can verify the repository-specific settings.

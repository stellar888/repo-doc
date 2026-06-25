# repo-doc

Documentation drift starts quietly. A route changes here, a flag gets renamed there, and the docs
fall one small step behind the code. `repo-doc` is a cautious little agent for catching that moment
before it ships.

The agent accepts a Git diff, determines whether documentation needs to change, safely reads
relevant existing docs, and returns a reviewable Markdown proposal with a generated unified diff.
It uses LangGraph for stateful orchestration, LangChain's OpenAI integration for structured model
outputs, deterministic Python safety gates, Promptfoo for black-box evaluations, Pytest for unit
tests, and GitHub Actions for CI.

It is intentionally not a swaggering autonomous coding bot. It has a narrower personality: read
the diff, inspect only allowed docs, make a grounded suggestion, and ask for human review when the
evidence gets weird.

```text
                               __
   ________  ____  ____   ___ / /___  _____
  / ___/ _ \/ __ \/ __ \ / __  / __ \/ ___/
 / /  /  __/ /_/ / /_/ /  /_/ /_/ / / /__
/_/   \___/  ___/\____(_)_____\____/\___/
          /_/
```

## Why this architecture?

The design goal is useful help without spooky action at a distance. The outer workflow is
deterministic:

1. Validate and truncate the incoming diff.
2. Detect suspicious prompt-injection-like content.
3. Ask the model for structured impact analysis.
4. Merge model-selected documentation paths with repository-discovered candidates.
5. Ask the model for a bounded documentation proposal using that context.
6. Generate unified diffs from trusted application code.
7. Apply deterministic path, schema, and content checks.
8. Return a reviewable result by default, or write documentation only when `--apply` is used.

The model can recommend changes but cannot execute shell commands, read secrets, write outside
approved documentation paths, commit, merge, or deploy code.

In other words: the model gets a pencil, not the keys to the building.

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

## Quick Start: Existing Repo

Use this path when the repository already has at least a `README.md`, `docs/`, or similar
documentation location.

```bash
cd /path/to/your/project
python -m pip install repo-doc
repo-doc init --ci --include-agents-doc
repo-doc check --base main --format agent-json --quiet --output repo-doc-agent.json
```

Commit the generated `repo-doc.toml` and `.github/workflows/repo-doc.yml`. Then add an
`OPENAI_API_KEY` repository secret in GitHub Actions settings so PR checks can run model-backed
analysis. For deterministic demos or repos where no secret should be used, generate the workflow
with `--ci-mock`.

```bash
repo-doc init --ci --include-agents-doc --ci-mock
```

## Quick Start: Blank Repo

Use this path when the repository has no docs and no agent guidance yet. `repo-doc init` creates
configuration and CI workflow files; it does not invent your first project description. Add a small
human-owned baseline first, then let repo-doc keep it from drifting.

```bash
cd /path/to/blank/project
python -m pip install repo-doc

cat > README.md <<'EOF'
# Project Name

Briefly describe what this project does, who uses it, and the main way to run or use it.
EOF

cat > AGENTS.md <<'EOF'
# Agent Instructions

Keep changes scoped, update README.md or docs/ when behavior changes, and stop for human review
when secrets, credentials, or unclear product behavior appear in the diff.
EOF

repo-doc init --ci --include-agents-doc
repo-doc check --base main --format agent-json --quiet --output repo-doc-agent.json
```

Commit these starter files:

```bash
git add README.md AGENTS.md repo-doc.toml .github/workflows/repo-doc.yml
git commit -m "Add repo-doc documentation gate"
```

On GitHub, add `OPENAI_API_KEY` under repository settings, in Actions secrets. If the repository
accepts pull requests from forks, remember that GitHub does not pass repository secrets to
untrusted fork PRs by default; use `--ci-mock`, a trusted-run workflow, or a separate policy for
external contributors.

## Daily Use

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

Allow the agent to create or update root-level coding-agent guidance when a repository wants that
as part of its docs:

```bash
repo-doc analyse --include-agents-doc
```

Or commit a `repo-doc.toml` to each repository that uses the tool:

```toml
allowed_doc_paths = ["docs", "README.md", "guides"]
include_agents_doc = true
base_branch = "main"
max_diff_chars = 40000
max_doc_chars = 12000
openai_model = "gpt-5-mini"
```

There is a copyable starter at `repo-doc.example.toml`.

You can generate the starter instead:

```bash
repo-doc init --include-agents-doc
repo-doc init --ci --include-agents-doc
```

The output is JSON. The important fields are:

- `status`: `ok`, `human_review`, or `blocked`.
- `analysis`: the model's structured explanation of documentation impact.
- `proposal.edits`: proposed Markdown changes.
- `proposal.edits[].operation`: `create_file`, `append_section`, or `replace_section`.
- `proposal.edits[].unified_diff`: a patch-style review artifact.

The tool never commits, merges, deploys, or opens pull requests automatically. Without `--apply`,
it only proposes changes and generates reviewable diffs.

## Output formats

JSON is the default because it is stable for automation:

```bash
repo-doc analyse --format json
```

For coding agents and automation, emit the compact action contract:

```bash
repo-doc check --format agent-json --quiet
```

`agent-json` includes `next_action`, `check_exit_code`, `can_apply`, candidate files, edit paths,
safety flags, reviewer notes, model metadata, and the prompt version. Use `--quiet` when another
agent needs clean stdout to decide whether to continue, update docs, or stop for review.

For humans, generate a Markdown preview:

```bash
repo-doc analyse --format markdown --output repo-doc-preview.md
```

The Markdown report includes the status, summary, findings table, candidate files, proposed
Markdown, generated diff, reviewer notes, and safety flags. For a nicer terminal rendering, use
Rich-flavored Markdown output:

```bash
repo-doc analyse --format rich
```

Useful settings:

- `OPENAI_MODEL`: model used by LangChain's OpenAI chat client.
- `ALLOWED_DOC_DIRS`: comma-separated documentation paths the agent may read or propose edits for.
- `INCLUDE_AGENTS_DOC`: set to `true` to include `AGENTS.md` in the allowed documentation paths.
- `REPOSITORY_ROOT`: root used when reading existing documentation when `--repo-root` is omitted.
- `MAX_DIFF_CHARS` and `MAX_DOC_CHARS`: input caps before model calls.

## GitHub Actions check

The easiest CI path is the bundled GitHub Action:

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
      - uses: stellar888/repo-doc@v0.5.0
        with:
          base: origin/${{ github.base_ref }}
          include-agents-doc: "true"
          output-file: repo-doc-agent.json
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

The action installs repo-doc, runs `repo-doc check --format agent-json --quiet`, uploads the
result artifact by default, and exposes outputs such as `status`, `next-action`, `can-apply`, and
`result-file`.

To generate a starter workflow in another repository:

```bash
repo-doc init --ci --include-agents-doc
```

Use mock mode for deterministic CI demos that do not need an API key:

```yaml
- uses: stellar888/repo-doc@v0.5.0
  with:
    base: origin/${{ github.base_ref }}
    mock: "true"
```

Run tests:

```bash
pytest
ruff check .
mypy
python -m build
python -m pip install --force-reinstall --no-deps dist/*.whl
repo-doc --version
repo-doc --help
```

Run Promptfoo evaluations:

```bash
PROMPTFOO_PYTHON=.venv/bin/python npx --yes promptfoo@latest eval -c evals/promptfooconfig.yaml \
  -o artifacts/promptfoo.json \
  -o artifacts/promptfoo.html
```

Promptfoo invokes the application through a Python provider, meaning it evaluates the complete
graph rather than merely evaluating an isolated prompt. If you use a local virtualenv, set
`PROMPTFOO_PYTHON=.venv/bin/python` so Promptfoo starts the provider with the same dependencies.
The deterministic suite emits and asserts the `agent-json` contract, including routing for API
docs, README configuration docs, `AGENTS.md`, human review, and safety blocking.

## Production improvements

- Add embeddings or richer repository indexing for large documentation sets.
- Use a GitHub App instead of a broadly scoped personal token.
- Add a model gateway, tracing, cost budgets, and audit storage.
- Add human-labelled evaluation cases from production incidents.
- Execute documentation builds in an isolated runner.
- Create pull requests through a narrow tool service rather than giving the model GitHub access.
- Add OIDC only when a workflow actually needs cloud access.

## Configuration details

You can commit `repo-doc.toml` at the root of any repository that uses this tool. That gives the
agent local house rules: where docs live, which base branch CI should compare against, and how much
context it may read.

Supported keys can be top-level or nested under `[tool."repo-doc"]`:

- `allowed_doc_paths`: paths or directories the agent may read or propose edits for.
- `include_agents_doc`: whether to also allow creating or updating root-level `AGENTS.md`.
- `base_branch`: default branch ref for CI-oriented checks when no `--base` is provided.
- `max_diff_chars`: maximum diff input size passed to the agent.
- `max_doc_chars`: maximum document size the agent will read.
- `openai_model`: optional model override for the repository.

```toml
allowed_doc_paths = ["docs", "README.md", "guides"]
include_agents_doc = true
base_branch = "main"
max_diff_chars = 40000
max_doc_chars = 12000
openai_model = "gpt-5-mini"
```

Discovery and precedence:

- By default, `repo-doc.toml` is read from the repository root.
- Use `--config-file` to point at a different file.
- CLI flags take priority over `repo-doc.toml`.
- Values not set in the config fall back to environment variables and built-in defaults.

## Check details

Use `repo-doc check` when you want a CI gate instead of an interactive review flow. It still prints
the structured JSON result, but the exit code is the main signal.

Typical places to run it:

- GitHub Actions pull-request jobs.
- Pre-push hooks.
- Release checks before cutting a tag.

Exit codes:

- `0`: no documentation update is required.
- `2`: documentation updates are needed.
- `3`: human review is required.
- `4`: a deterministic safety gate blocked the run.

Examples:

```bash
repo-doc check --base origin/main
repo-doc check --base origin/main --mock
repo-doc check --config-file /path/to/repo-doc.toml --base origin/main
```

Base-branch resolution:

- If you pass `--base`, that value is used.
- If you pass `--diff-file` or `--staged`, no base branch is inferred.
- Otherwise, `check` uses `base_branch` from `repo-doc.toml` when present.

## Doctor

`repo-doc doctor` validates local configuration without calling a model. Use it when a repository
has its own config and you want to see exactly what the agent will believe before it thinks too
hard about your diff.

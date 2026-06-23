# AI Repository Maintenance Agent

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
8. Return a reviewable result; never merge or deploy automatically.

The model can recommend changes but cannot execute shell commands, read secrets, write outside
approved documentation paths, or merge code.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Run safely without an API key:

```bash
repo-doc-agent analyse --diff-file examples/api-change.diff --mock
```

Run with OpenAI:

```bash
export OPENAI_API_KEY="..."
repo-doc-agent analyse --diff-file examples/api-change.diff
```

Useful settings:

- `OPENAI_MODEL`: model used by LangChain's OpenAI chat client.
- `ALLOWED_DOC_DIRS`: comma-separated documentation paths the agent may read or propose edits for.
- `REPOSITORY_ROOT`: root used when reading existing documentation.
- `MAX_DIFF_CHARS` and `MAX_DOC_CHARS`: input caps before model calls.

Run tests:

```bash
pytest
ruff check .
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

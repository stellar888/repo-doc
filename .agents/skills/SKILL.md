---
name: repo-doc-agentic-docs
description: Use when a coding agent needs to run repo-doc as a documentation-impact gate, interpret its agent-json contract, update documentation safely, or integrate repo-doc into pre-commit, CI, or agentic developer flows.
---

# Repo-Doc Agentic Documentation Workflow

Use repo-doc as a bounded documentation safety rail. Prefer deterministic checks, mock mode for
local validation, and `agent-json` for machine-readable decisions.

## Quick Workflow

1. Initialize config when a repository has none:

   ```bash
   repo-doc init
   repo-doc init --include-agents-doc
   ```

2. Check the current work:

   ```bash
   repo-doc check --format agent-json --quiet --output repo-doc-agent.json
   ```

3. Read `repo-doc-agent.json` and branch on `next_action`:

   - `no_documentation_change`: continue.
   - `update_documentation`: inspect proposed files and update docs.
   - `request_human_review`: stop and ask for review.
   - `stop_for_safety_review`: stop; do not apply changes.

4. For a human-readable preview:

   ```bash
   repo-doc analyse --format markdown --output repo-doc-preview.md
   ```

5. Apply only when the result is safe:

   ```bash
   repo-doc analyse --apply
   ```

## Agent-JSON Fields

Use these fields as the stable automation contract:

- `status`: `ok`, `human_review`, or `blocked`.
- `next_action`: recommended control-flow action.
- `check_exit_code`: expected CI-style exit code.
- `can_apply`: whether an automated apply path is safe.
- `candidate_files`: documentation files considered.
- `edit_paths`: files with proposed edits.
- `edits[].operation`: `create_file`, `append_section`, or `replace_section`.
- `safety_flags`: deterministic safety issues.
- `reviewer_notes`: model or validator notes for a human.

## Safety Rules

- Never continue automatically when `status` is `blocked`.
- Never apply when `can_apply` is false.
- Treat `human_review` as a stop-and-ask state, not a soft warning.
- Do not run live model-backed checks unless the user or workflow provides an API key intentionally.
- Use `--mock` for deterministic demos, tests, and documentation examples.

## Common Commands

Validate a built package before reinstalling or publishing:

```bash
python -m build
python -m pip install --force-reinstall --no-deps dist/*.whl
repo-doc --version
repo-doc --help
```

Run Promptfoo contract evaluations:

```bash
PROMPTFOO_PYTHON=.venv/bin/python npx --yes promptfoo@latest eval -c evals/promptfooconfig.yaml
```

Run against staged changes:

```bash
repo-doc check --staged --format agent-json --quiet --output repo-doc-agent.json
```

Run against a base branch:

```bash
repo-doc check --base origin/main --format agent-json --quiet --output repo-doc-agent.json
```

Run from another working directory:

```bash
repo-doc check --repo-root /path/to/repo --format agent-json --quiet --output repo-doc-agent.json
```

Allow `AGENTS.md` as documentation:

```bash
repo-doc check --include-agents-doc --format agent-json --quiet --output repo-doc-agent.json
```

## Expected Agent Behavior

- Update docs manually when `next_action=update_documentation` and `can_apply` is false.
- Prefer reviewing `proposal.edits[].unified_diff` before writing.
- Keep doc changes scoped to `documentation_files`.
- Re-run repo-doc after changing docs.
- Report safety flags plainly in the final response.

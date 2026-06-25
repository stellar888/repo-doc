# CI integration and the check command

repo-doc provides a CI-friendly command named check that is intended for use as a deterministic documentation gate in continuous integration pipelines.

Why use check instead of analyse?

- check is designed to be non-interactive and to return deterministic exit codes so CI jobs can succeed or fail based on the documentation status without parsing JSON.
- It still prints a JSON payload to stdout for debugging or artifact storage, and it supports an --output file for CI artifacting.
- For agentic workflows, --format agent-json --quiet emits a compact contract with next_action, check_exit_code, can_apply, documentation files, and safety flags.

Exit codes

- 0: No documentation update required.
- 2: Documentation updates are needed (treat as failure in CI to block merges until docs are updated).
- 3: Human review required (signal to route to a reviewer instead of automatically failing with a fix suggestion).
- 4: Blocked by a deterministic safety gate (do not proceed automatically).

Recommended GitHub Actions pattern

- Ensure your checkout step fetches sufficient history so that the base branch ref (if used) can be resolved (fetch-depth: 0 is common).
- Typical usage is to pass a base ref such as origin/main to compare the feature branch with main:

```yaml
- run: repo-doc check --base origin/main
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

- For deterministic demonstrations or when an API key is not available in the demo environment, use --mock to avoid external model calls:

```bash
repo-doc check --base origin/main --mock
```

Agent-friendly output

```bash
repo-doc check --base origin/main --format agent-json --quiet --output repo-doc-agent.json
```

Use next_action and can_apply when another coding agent needs to decide whether to continue,
apply documentation changes, request human review, or stop for a safety issue.

Package smoke test

The reusable CI workflow also builds the package and smoke-tests the installed wheel:

```bash
python -m build
python -m pip install --force-reinstall --no-deps dist/*.whl
repo-doc --version
repo-doc --help
repo-doc check --diff-file examples/no-doc-change.diff --mock --format agent-json --quiet
```

Base-branch resolution details

When check runs against committed changes it needs a base ref to compute the diff. The effective base is chosen like this:

1. Use the explicit --base if provided.
2. If --diff-file or --staged is in use, do not fall back to repo-doc.toml's base_branch (the command analyses the provided diff or staged changes directly).
3. Otherwise, if no explicit --base and neither --diff-file nor --staged were provided, check will use base_branch from repo-doc.toml if that key is present.

Notes

- If you rely on a repository-local base_branch, make sure repo-doc.toml is present in the repo or pass --config-file to point at it during CI.
- The CLI flag --allowed-doc-path overrides repo-doc.toml and any ALLOWED_DOC_DIRS environment variable; use this intentionally when you need to temporarily expand or restrict allowed documentation paths for a job.

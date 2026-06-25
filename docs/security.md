# Security model

- Repository content is explicitly labelled as untrusted.
- Suspicious instructions are flagged before model execution.
- Secret-like diff input blocks the run before model execution.
- Existing documentation is read only from configured allowed paths.
- Secret-like existing documentation content is redacted before model execution.
- The model has no shell, network, GitHub, or secrets tool.
- Output is constrained using Pydantic schemas.
- Proposed paths must stay inside configured documentation paths.
- Secret-like output causes the run to be blocked.
- Suspicious input causes human review.
- Forbidden candidate documentation paths cause the run to be blocked.
- Documentation writes require explicit `--apply`, only write allowed documentation paths, and
  refuse `human_review`, `blocked`, and `no_change` results.
- The tool never commits or merges.
- GitHub Actions uses `contents: read`.
- API-backed evaluations should not run on untrusted fork pull requests with secrets.

Prompt-level protections are defence in depth, not the security boundary. Permissions and
deterministic validators remain authoritative.

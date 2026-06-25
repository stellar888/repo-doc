# repo-doc configuration (repo-doc.toml)

This file lets a repository provide sensible defaults for repo-doc without requiring every CI job or developer to pass the same flags. The file is optional.

Create a starter config

```bash
repo-doc init
repo-doc init --include-agents-doc
```

The init command detects common documentation paths such as docs, guides, documentation, and README.md. It refuses to overwrite an existing repo-doc.toml unless --force is provided.

Location and discovery

- Default: REPO_ROOT/repo-doc.toml
- You can point at a different file with the CLI option --config-file.
- The TOML may be provided either as a top-level table or nested at [tool."repo-doc"]. The loader will detect and use the inner table if present.

Supported keys

- allowed_doc_paths (array[string], optional)
  - A list of paths or directories the agent is allowed to read and propose edits for (e.g. ["docs", "README.md"]). When present, these are applied to the runtime allowed_doc_dirs setting.

- include_agents_doc (boolean, optional)
  - When true, AGENTS.md is appended to the allowed documentation paths so repo-doc may read, create, or update root-level coding-agent guidance.

- base_branch (string, optional)
  - A default base ref used by CI-oriented flows when a CLI --base is not provided and when the command is running against committed changes (see docs/ci.md for the check command's resolution rules).

- max_diff_chars (integer, optional)
  - Caps the diff input size sent to the model.

- max_doc_chars (integer, optional)
  - Caps individual document sizes the agent will read.

- openai_model (string, optional)
  - Optional model identifier to prefer for that repository.

Precedence and mapping

- CLI flags take precedence over repo-doc.toml. For example, repeating --allowed-doc-path on the CLI overrides allowed_doc_paths from the TOML and the ALLOWED_DOC_DIRS environment variable.
- Values from repo-doc.toml are applied into the tool's runtime settings (allowed_doc_dirs, include_agents_doc, max_diff_chars, max_doc_chars, openai_model) when present.

Examples

Top-level table:

```toml
allowed_doc_paths = ["docs", "README.md"]
include_agents_doc = true
base_branch = "main"
max_diff_chars = 40000
```

Nested under the tool table (also supported):

```toml
[tool."repo-doc"]
allowed_doc_paths = ["docs"]
include_agents_doc = true
base_branch = "main"
```

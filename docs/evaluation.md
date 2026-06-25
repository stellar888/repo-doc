# Evaluation strategy

## Layer 1: deterministic unit tests

Pytest covers path validation, safe documentation reads, injection detection, graph routing,
generated patches, and output status.

## Layer 2: black-box scenario evaluation

Promptfoo invokes the complete application through `evals/provider.py`. By default, the provider
uses the deterministic mock model and emits the same `agent-json` contract that coding agents
consume in CI or local automation.

The suite checks:

- JSON contract validity, including `schema_version`, `next_action`, and `check_exit_code`
- documentation update routing for API, configuration, and coding-agent workflow changes
- correct abstention for internal refactors
- prompt-injection routing to human review
- secret-like input blocking before model execution and secret non-disclosure

Run the deterministic suite from the repository root. When using the local virtualenv, set
`PROMPTFOO_PYTHON=.venv/bin/python` so Promptfoo starts the provider with the same Python
dependencies as the CLI:

```bash
PROMPTFOO_PYTHON=.venv/bin/python npx --yes promptfoo@latest eval -c evals/promptfooconfig.yaml \
  -o artifacts/promptfoo.json \
  -o artifacts/promptfoo.html \
  -o artifacts/promptfoo.junit.xml
```

The provider accepts config values in `evals/promptfooconfig.yaml` for `mock`, `output_format`,
`repo_root`, `allowed_paths`, `include_agents_doc`, `max_diff_chars`, `max_doc_chars`, and
`openai_model`.

## Layer 3: model-backed semantic evaluation

For a production exercise, switch the provider from mock to OpenAI and add rubric assertions for:

- factual grounding in the diff
- completeness of documentation impact
- absence of unsupported claims
- usefulness to a human reviewer

Model judges should be calibrated against human-labelled cases and should not be the only gate for
security-critical behaviour.

## Recommended metrics

- task success rate
- critical-case pass rate
- false-positive documentation rate
- abstention correctness
- invalid schema rate
- average latency
- input/output tokens
- estimated cost
- variance across repeated runs

# Evaluation strategy

## Layer 1: deterministic unit tests

Pytest covers path validation, safe documentation reads, injection detection, graph routing,
generated patches, and output status.

## Layer 2: black-box scenario evaluation

Promptfoo invokes the complete application through `evals/provider.py`. Assertions check JSON
validity, task outcome, abstention, injection handling, generated edit location, and secret
non-disclosure.

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

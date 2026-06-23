# Architecture

`repo-doc` is meant to feel like a careful reviewer, not a runaway automation. It can notice that
your code and docs may be drifting apart, gather a narrow slice of context, and draft a patch. It
does not get shell access, broad filesystem access, or permission to merge its own work.

The personality of the system is simple: helpful, bounded, and willing to say "human review" when
the evidence is not clean enough.

## Trust boundaries

Trusted:

- Versioned system policy
- Application source code
- Allowed-path configuration
- Deterministic validators
- CI branch protection

Untrusted:

- Git diffs
- Issue text
- Pull-request descriptions
- Repository comments and documentation
- Model output

The model never receives secrets and never receives a general shell tool. Model output is parsed
into Pydantic schemas and then checked by deterministic validators.

## LangGraph workflow

```text
START
  |
prepare
  |
analyse
  |--------------------|
no documentation       documentation impact
  |                    |
no_change           read_docs
  |                    |
  |                 propose
  |                    |
  |                  patch
  |                    |
  -------- validate ----
              |
             END
```

Each node has a narrow contract. Conditional routing is based on parsed state, documentation reads
are limited to configured paths, generated patches come from trusted application code, and every
terminal path passes through deterministic validation.

## Why LangGraph?

This project could be a plain Python pipeline. LangGraph is included to demonstrate explicit
state, nodes, edges, conditional routing, and future extension points such as checkpoints or human
approval. The framework is not being used as a substitute for designing the workflow.

## Why Promptfoo?

Pytest verifies Python behaviour and hard invariants. Promptfoo treats the graph as a black-box AI
application and verifies scenario-level behaviour across a dataset. In a real deployment, the same
suite would compare prompt or model candidates against a pinned baseline.

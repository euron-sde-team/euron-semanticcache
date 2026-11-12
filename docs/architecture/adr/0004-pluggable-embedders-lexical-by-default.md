# ADR-0004: Pluggable embedders, lexical by default

- **Status:** Accepted

## Decision

The default `HashingEmbedder` needs no model download and no network, and is deterministic, so the stack runs on a
laptop and in CI with exact assertions. `OpenAICompatEmbedder` calls any `/embeddings` endpoint for real semantic
matching, selected with `SC_EMBEDDER=openai`.

## Consequences

- The out-of-the-box experience works offline, and every test is reproducible.
- The default catches rewording, casing, stop-words and typos in wording, but not deep paraphrase. The documentation
  says so plainly and the similarity lab shows the scores, so a team can decide to switch.
- Vectors from different embedders are not comparable; the index ignores entries of a different dimension.

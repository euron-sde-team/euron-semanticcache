# ADR-0002: Deterministic guards on top of similarity

- **Status:** Accepted

## Context

Embeddings measure topical closeness, not truth conditions. "Report for region 4" and "region 5", "error E404" and
"error E500", "do cats like milk" and "don't cats like milk" are nearly identical vectors with different answers.
A threshold cannot separate them without also rejecting legitimate paraphrases.

## Decision

After the threshold, a candidate must also agree on the set of numbers, the set of letter-digit identifiers, and the
presence of negation. These are cheap, deterministic and explainable. They can be switched off per namespace.

## Consequences

- A whole class of confident wrong answers is removed, and the playground and the similarity lab say which guard fired.
- Some true paraphrases are rejected (for example a number written as a word above twenty). The cost is a provider call,
  never a wrong answer.
- Guards do not make semantic matching safe in general. They remove the most common failure, not all of them.

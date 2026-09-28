# Canonical Query Coverage Benchmark

This benchmark turns the v6.6 canonical Tier-1/Tier-2 vocabulary audit into a
retrieval gate.

## What it proves

For every multi-word canonical Tier-1/Tier-2 entity that is present in the
canonical claims corpus, the production KnowledgeQueryEngine must:

1. recognize the entity in a deterministic factual query;
2. return evidence-backed output; and
3. pass additional source/update/requirement/numeric/event query cases only
   when the supporting canonical claims actually contain evidence for that
   intent.

The benchmark therefore tests **retrievability**, not gold factual accuracy.
It does not manufacture missing values or convert community/YouTube evidence
into canonical truth.

## Failure policy

Any generated case that becomes unparseable or evidence-empty fails CI. This
makes a canonical vocabulary/retrieval regression visible immediately instead
of waiting for a player to discover it on the website.

The next layer after this gate is a gold/rubric factual benchmark, which must
measure answer correctness separately from retrieval coverage.

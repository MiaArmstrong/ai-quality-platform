# Knowledge Governance

## Source hierarchy

Current executable behavior, canonical shared documentation, approved work-item
criteria, validated operational memory, working notes, and agent inference form
an explicit authority hierarchy. Conflicts are surfaced rather than silently
resolved.

## Canonical shared knowledge

The GitHub Wiki is the intended canonical team knowledge base for durable
architecture, behavior, integration contracts, test strategy, constraints, and
operational guidance.

## Working memory

`knowledge/mempalace/` stores narrow operational history, investigation context,
debugging heuristics, and pointers. It is not automatically authoritative.

`knowledge/wiki-map.md` is a lightweight index of stable Wiki page names. It
must not duplicate full page content.

## Promotion rules

Promote knowledge when it is validated, stable, broadly reusable, and worth
maintaining for more than one task or person. Search first, update rather than
duplicate, preserve provenance, and replace redundant working-memory detail with
a canonical pointer where practical.

## Conflict and staleness

When code, Wiki content, criteria, or working memory disagree, record the sources,
freshness, and evidence strength. Potentially stale content remains flagged until
verified; executable behavior can itself be defective and is not assumed correct
without review.

## Privacy

Never place credentials, tokens, private keys, customer data, confidential
payloads, or unredacted production logs in the Wiki or working memory.

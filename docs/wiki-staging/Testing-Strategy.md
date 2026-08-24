# Testing Strategy

## Contract validation

`tools/validate_contracts.py` checks registry and workflow schemas, referenced
files, role/skill/standard dependencies, capabilities, tiers, verdict enums,
required gates, artifact I/O declarations, outcome transitions, and duplicate
IDs or transitions.

## Offline tests

Deterministic mocks test workflow transitions, authorization, gates, persistence,
routing, provider adaptation, canonical and semantic validation, repair,
redaction, and crash recovery without provider network calls. Current `main`
passes 79 offline tests.

## Provider smoke testing

The optional OpenAI smoke test is disabled by default. When explicitly enabled,
it runs only the Architect reasoning path, sends no tools, performs no outward
actions, and validates both declared artifacts. Provider usage, latency, attempts,
repair, routing, and artifact validation are recorded.

## Adversarial verification

Verification attempts to prove a result wrong: it looks for vacuous tests,
unobserved authoritative state, bypassable authorization, stale evidence,
unsafe recovery, and discrepancies between telemetry and persisted state.

PR #1's adversarial review found multiple trust-boundary defects despite a green
suite. Negative tests and runtime fixes were added before merge. Green tests are
necessary evidence, not proof that the intended guarantees cannot be bypassed.

## Failure classification

Failures are classified as `PRODUCT`, `TEST`, `ORCHESTRATION`, `ENVIRONMENT`, or
`UNKNOWN`. Insufficient evidence must not be converted into a product defect just
to produce a conclusion.

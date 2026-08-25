# Testing Strategy

## Contract validation

`tools/validate_contracts.py` checks registry and workflow schemas, referenced
files, role/skill/standard dependencies, capabilities, tiers, verdict enums,
required gates, artifact I/O declarations, outcome transitions, and duplicate
IDs or transitions.

## Offline tests

Deterministic mocks test workflow transitions, authorization, gates, persistence,
routing, provider adaptation, canonical and semantic validation, repair,
redaction, and crash recovery without provider network calls. The multi-role
provider workflow feature branch passes 101 offline tests.

## Provider smoke testing

Optional OpenAI demonstrations are disabled by default. The Architect smoke path
and the controlled `qa-provider-demo` paths send no tools, perform no outward
actions, and validate their declared artifacts. The multi-role demonstrations
cover both bounded ambiguity escalation and successful progression through
Requirements Analyst, deterministic QA Intake, and Adversarial Verifier to a
pending human `qa_signoff` gate. Provider usage, latency, attempts, repair,
routing, artifact validation, and bounded sanitized results are recorded.

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

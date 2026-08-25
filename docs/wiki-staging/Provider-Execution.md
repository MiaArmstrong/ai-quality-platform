# Provider Execution

## Neutral interface

Provider requests carry role-scoped instructions, skills, standards, task and
workflow context, input artifacts, logical model tier, output contract,
authorization context, source hashes, attempt number, and repair context. Model
access does not grant tools or action capabilities.

## OpenAI adapter

The first adapter uses OpenAI's Responses API and strict Structured Outputs. It
projects canonical schemas onto the provider-supported schema subset, rejects
incompatible schemas locally, and sends no model tools. Requests explicitly set
`store=False`, which disables Responses application-state storage but does not
override broader documented provider retention or abuse-monitoring controls.

## Validation and repair

The provider-neutral boundary never trusts adapter-reported validity. It checks
the execution envelope and each canonical artifact contract before semantic
validation. Architect semantic rules currently reject contradictory escalation
state and escalation requests when no higher tier exists.

Repairable invalid output receives one repair attempt. The original and repaired
responses remain distinct local evidence. Artifacts are accepted only after both
schema and semantic validation pass.

## Attempt lifecycle and telemetry

Network attempts receive a correlation ID and are committed as `IN_PROGRESS`
before dispatch. They finalize with provider/model identity, response ID,
latency, token usage, validation results, repair status, source hashes, and safe
errors. An unresolved attempt is not automatically retried.

Default inspection omits raw provider output. Raw evidence remains local SQLite
data and is ignored by source control.

## Current milestone

Architect has completed a successful real-provider, reasoning-only smoke test
producing `automation_design` and `sources_of_record`, with no tools, outward
actions, or repair. Requirements Analyst and Adversarial Verifier are also
real-provider-demonstrated through the opt-in `qa-provider-demo`; QA Intake is a
canonically validated deterministic step. Other roles remain mock-backed unless
explicitly enabled, and no economy-tier role has completed a real-provider run.

The opt-in multi-role demo enforces configured request budgets before dispatch:
32,000 estimated compiled input tokens and 4,096 output tokens per request.
Input estimation uses `tiktoken` with a protocol-overhead allowance and is not
claimed to equal server accounting. Requests are rejected rather than truncated.
Observed cost telemetry distinguishes normal input, cached reads, cache writes,
and output when all required usage fields are available; otherwise cost is null.

## Controlled multi-role evidence

The first controlled run intentionally supplied ambiguous divide-by-zero
behavior. The standard Requirements Analyst naturally requested escalation,
the high-reasoning Requirements Analyst found no responsible resolution and
requested further escalation, and the runtime stopped at
`INSUFFICIENT_EVIDENCE` because no higher tier was available. It made two
provider calls and recorded an observed estimated cost of `$0.0993205`. QA
Intake, Adversarial Verifier, and the human gate were not reached.

The second controlled run supplied an explicit `DIVIDE_BY_ZERO` product
decision. Requirements Analyst succeeded through Terra, deterministic QA Intake
passed canonical validation, and Adversarial Verifier succeeded through Sol.
The workflow stopped at the pending human `qa_signoff` gate; the gate was not
auto-approved. It made two provider calls and recorded 5,935 input tokens, 3,173
output tokens, 5,929 cache-write tokens, 43,933 ms provider latency, and an
observed estimated cost of `$0.0694375`, with no repairs, escalations, or
validation failures. Artifact fields lost from the original truncated sanitized
report are intentionally not reconstructed.

Demo reporting now extracts a bounded non-sensitive summary before temporary
SQLite cleanup. It includes accepted canonical verdicts and selected findings,
verifier conclusions, gate-bound artifact/evidence hashes, workflow/gate state,
and aggregate telemetry. It excludes raw provider output, recursively bounds
selected detail, and explicitly falls back to priority fields if the full
sanitized report would exceed its size limit.

These demonstrations did not enable real filesystem, shell, GitHub, Wiki,
deployment, ticketing, or other side-effect adapters. The runtime remains
single-runner.

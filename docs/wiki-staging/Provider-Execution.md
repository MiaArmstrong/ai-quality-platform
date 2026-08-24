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
actions, or repair. Other roles remain mock-backed unless future work explicitly
enables them.

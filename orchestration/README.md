# Executable Orchestration Vertical Slice

This package compiles and executes the provider-neutral `automate` workflow.
The deterministic mock remains the offline default; selected read-only roles
can be routed through a provider adapter.

It intentionally does not contain action adapters, real shell/test execution,
filesystem mutation, Wiki writes, ticket writes, or deployment behavior.

## Provider adapter

`ExecutionRequest` and `ExecutionResult` are vendor-neutral. The context compiler
loads only the selected role, declared skills and standards, supplied artifacts,
workflow/authorization context, and output contract. It records SHA-256 hashes
for every contributing instruction file.

The OpenAI adapter uses the Responses API with strict JSON Schema output per the
official [Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs).
The runtime validates output again, preserves malformed originals and errors,
and permits one explicit repair attempt. An `escalate` result creates a new
attempt only through a registry-approved tier transition.

Schema-valid provider output then passes through a provider-neutral semantic
validation stage before any artifact is accepted. Semantic findings use the
versioned `.agents/schemas/semantic-validation-result.v1.schema.json` contract
with `VALID`, `INVALID`, and `WARNING` results. `INVALID` repairable output is
preserved as provider-attempt evidence and receives the same single repair
opportunity; artifacts are persisted only after schema and semantic validation
both pass. Failed repair leaves the workflow in `FAILED` with both raw responses,
structured findings, triggered rule IDs, and repair telemetry retained.

The initial Architect rules reject a successful result that simultaneously sets
`automation_design.escalation_requested` and reject escalation requests when the
registered Architect role has no higher tier. This prevents highest-tier
escalation requests from being silently ignored.

Before any request, the adapter projects canonical contracts onto OpenAI's
documented Structured Outputs subset and validates every nested object,
required field, and keyword. Constraints not supported by the provider (such as
`minLength`) remain in the canonical contract and are enforced after response;
unsafe composition keywords fail locally. HTTP 400 diagnostics expose only
status, error type/code, parameter, and a sanitized bounded message.

Model access grants no tool or action authority. The adapter exposes no tools;
declared actions are independently checked by `AuthorizationService`. This is
an application-level control, not an OS sandbox.

Install the optional dependency with `pip install -r requirements-provider.txt`.
Configure logical tiers without putting model IDs in roles or workflows:

```text
OPENAI_API_KEY=<secret>
AQP_OPENAI_MODEL_ECONOMY=<model-id>
AQP_OPENAI_MODEL_STANDARD=<model-id>
AQP_OPENAI_MODEL_HIGH_REASONING=<model-id>
```

Telemetry records provider, model, latency, attempt, input/output tokens, cached
tokens when available, semantic-validation status/findings/rule IDs, repair
attempt/success, and cost only when pricing is explicitly configured.

The optional smoke test is disabled by default and runs one harmless, read-only
Architect task with no tools or outward actions. Success requires both declared
Architect artifacts (`automation_design` and `sources_of_record`) to pass their
individual contracts. The smoke test permits one initial provider attempt and
one repair attempt only for invalid structured output; Architect does not escalate:

```text
$env:AQP_RUN_OPENAI_SMOKE='1'
python tools/smoke_openai_provider.py
```

## Commands

```text
python -m orchestration validate
python -m orchestration compile
python -m orchestration --db runtime.db start --work-item "Example work item"
python -m orchestration --db runtime.db inspect <run-id>
python -m orchestration --db runtime.db approve <run-id> --by <person> --reason <reason>
python -m orchestration --db runtime.db reject <run-id> --by <person> --reason <reason>
python -m orchestration --db runtime.db resume <run-id>
```

Gate decisions and resumes are separate commands so approval never implicitly
executes downstream work. SQLite holds runtime metadata and an append-only event
ledger. Artifact payloads are canonical JSON in SQLite for this slice; the
schema leaves room for future file-backed large artifacts.

## Demonstration

```text
python tools/demo_automate.py --db demo.db
```

The demonstration rejects and reworks both the design and release gates before
reaching `COMPLETED`.

## Authorization decisions

`authorization.py` evaluates role, capability, resource, task scope, and current
gate approvals. It returns `ALLOW`, `DENY`, or `REQUIRE_GATE` without performing
the requested action. The mock executor checks every action declared by a
workflow task, and the workflow event ledger records each decision.

Repository writes can be limited to task-authorized path prefixes; command
execution is limited by command category; and Wiki/external operations can be
limited by external-system category. Stale approvals and approvals for another
resource, capability, or policy version do not authorize an action.

Prompt instructions are not sufficient security boundaries because a model can
misinterpret or disregard prose. Future real adapters must enforce these machine
decisions immediately before acting.

```text
python tools/demo_authorization.py
```

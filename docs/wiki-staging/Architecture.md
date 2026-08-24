# Architecture

## System boundary

AI Quality Platform currently executes the `automate` workflow through a local,
single-runner Python runtime. Declarative contracts define the system; SQLite
stores runtime state and evidence; deterministic mocks are the offline default;
and an OpenAI Responses API adapter is the first real provider implementation.

The runtime does not contain real filesystem, shell, GitHub, Wiki, deployment,
or ticket-writing adapters. Capability authorization is application-level
governance and is not an operating-system sandbox.

## Contract layer

`.agents/agent-registry.yaml` connects roles, skills, standards, workflows,
capabilities, schemas, routing policy, and provider configuration. Versioned JSON
Schemas validate those documents. `orchestration/compiler.py` validates and
freezes them into a compiled snapshot with SHA-256 hashes for every referenced
instruction source.

Provider execution fails when a live role, skill, or standard no longer matches
the compiled hash. This prevents a run from silently consuming new instructions
under an older snapshot identity.

## Runtime and persistence

The runtime advances nodes through explicit transitions, records artifacts as
canonical JSON, and maintains an append-only event history alongside mutable
state projections. Provider attempts are committed as `IN_PROGRESS` before
dispatch and finalized after response or failure. An unresolved network attempt
blocks automatic retry; v1 can explicitly abandon it and fail the run.

The current runtime is intentionally single-runner. Leases, state-version
compare-and-swap, and concurrent resume protection are tracked in issue #2.

## Routing and execution

Roles select provider-neutral tiers: `economy`, `standard`, or
`high_reasoning`. Provider configuration resolves a tier to a concrete model.
Selected provider-backed roles use the provider-neutral executor; other roles
remain deterministic mocks.

## Validation chain

Provider responses pass through this acceptance sequence:

1. response envelope validation;
2. canonical artifact schema validation;
3. semantic cross-field validation;
4. one repair attempt when the violation is repairable;
5. authorization of each artifact write;
6. artifact persistence and downstream workflow transition.

Invalid attempts remain local evidence and are not accepted as workflow
artifacts.

## Human gates

Gate requests bind active artifacts by ID and content hash. Approval is checked
against active evidence immediately before it is recorded. Changed evidence
stales the gate and requires a new decision. Rejection follows an explicit
rework transition.

## Extension points

- additional provider adapters behind the neutral provider interface;
- additional provider-enabled roles with canonical output contracts;
- isolated action adapters behind capability checks;
- workflow warning policies and future semantic rule registration;
- concurrency controls for multiple runtime workers.

## Intentionally absent

- concurrent workers or distributed scheduling;
- OS-level sandboxing;
- real side-effect adapters;
- autonomous merge, deploy, or publication;
- broad provider enablement for every registered role.

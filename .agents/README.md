# Agent System

This directory contains reusable agent skills, role instructions, and shared operating standards.

```text
.agents/
├── skills/
├── roles/
└── standards/
```

Skills should reference shared standards rather than copying their content.

## Agent registry

`.agents/agent-registry.yaml` is the machine-readable registry for agent roles,
model tiers, skills, escalation behavior, and routing telemetry.

Role Markdown files define behavior.

The registry defines how the orchestration layer discovers and routes those roles.

Provider configuration maps logical tiers to environment-variable names; model
identifiers do not belong in role or workflow contracts. Versioned artifact
contracts govern structured model output. Knowledge publication uses its own
`knowledge_publication_approval` gate rather than release approval.

Do not duplicate detailed role instructions in the registry.

## Contract validation

Install the development dependencies and validate the declarative contracts:

```text
python -m pip install -r requirements-dev.txt
python tools/validate_contracts.py
python -m unittest discover -s tests -v
```

The validator checks registry, role, skill, standard, workflow, schema, tier,
verdict, and human-gate references. It does not execute workflows.

## Executable vertical slice

`orchestration/` contains the approved provider-neutral, mock-backed executable
slice for the `automate` workflow. See `orchestration/README.md` for commands and
scope boundaries. The `qa` and `release-testing` workflows remain declarative.

## Capability authorization

`.agents/capabilities.v1.json` is the central registry of stable, provider-neutral
capability IDs. Every role has a machine-readable `capability_policy` in
`agent-registry.yaml` declaring allowed, denied, gated, and scoped behavior.

Policies are default-deny. Gated capabilities require an approved, non-stale
gate loaded from runtime persistence and bound to the exact run, gate type,
policy version, capability, resource hash, and current evidence hashes. Caller-
constructed approval objects are not authority. Task-scoped write permissions
do not expand beyond paths explicitly supplied by the active task.

Executable workflow tasks declare every artifact read and write. The runtime
authorizes those actual I/O operations in addition to statically validating the
declarations. Provider output passes provider-neutral envelope, canonical
artifact, and semantic validation before persistence.

Role prompts remain useful behavioral guidance, but prompt text is not a security
boundary. Any future real tool adapter must call the authorization service and
refuse actions unless it returns `ALLOW`.

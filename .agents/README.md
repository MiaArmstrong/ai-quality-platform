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

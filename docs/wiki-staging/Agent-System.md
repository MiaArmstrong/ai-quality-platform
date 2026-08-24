# Agent System

## Contract types

- **Roles** define specialized responsibilities, evidence expectations, model
  tier defaults, escalation behavior, and handoffs.
- **Skills** define reusable workflows and may depend on other skills or shared
  standards.
- **Standards** hold shared engineering and QA rules that roles should not copy.
- **The registry** provides machine-readable wiring, stable IDs, capabilities,
  dependencies, routing policy, providers, and workflow references.
- **Workflow definitions** describe nodes, role ownership, required and produced
  artifacts, gates, declared actions, and allowed transitions.

## Context and handoffs

Front-door roles gather broad context and produce Sources of Record so downstream
roles can open authoritative files instead of rediscovering the entire system.
The context compiler loads only the selected role, its skill and standard
dependencies, supplied artifacts, workflow context, authorization context, and
output contract.

## Model tiers

`economy`, `standard`, and `high_reasoning` are logical, provider-neutral tiers.
Concrete model names belong in environment/provider configuration. Roles should
use the least-expensive tier that can reliably perform their responsibility and
escalate only through registered transitions.

## Human independence principle

Related models can share blind spots. Agent review is useful but is not treated
as independent human judgment. High-impact design and release decisions preserve
explicit human gates, with both the proposal and adversarial evidence available
for review.

## Current execution status

The `automate` workflow has an executable provider-neutral runtime. Architect is
the first real provider-backed role; offline mocks remain the default for the
rest. Registry presence does not imply that a role already executes against a
real provider.

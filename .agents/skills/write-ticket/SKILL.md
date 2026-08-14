---

name: write-ticket
description: >
  Guide a user through authoring a high-quality engineering work item.
  Supports Bug, Story, Task, Epic, Initiative, Spike, Improvement,
  New Feature, Idea, and Sub-task. Applies shared requirements and QA
  standards, validates the draft, and produces a reviewable ticket.
  Never invents missing facts and never performs external submission
  without explicit authorization.
---

# Write Ticket

## Purpose

Create a work item that an engineer or QA professional can pick up without having to invent critical requirements.

Use the shared standards under `.agents/standards/` rather than duplicating them here.

## Core rules

* Ask for missing required information instead of guessing.
* Gather one logical piece of information at a time.
* Distinguish user-provided facts from agent inference.
* Verify referenced repository artifacts when local access is available.
* Always produce a draft before any outward action.
* Never submit, publish, or create an external ticket without explicit authorization.
* Use observable, testable acceptance criteria.
* Keep severity and priority separate for bugs.
* Synthesize the Definition of Done for the specific ticket.
* Preserve links or references to supporting documentation.
* If requirements conflict, surface the conflict instead of silently resolving it.

## Flow

### 1. Determine work-item type

Supported types:

* Bug
* Story
* Task
* Epic
* Initiative
* Spike
* Improvement
* New Feature
* Idea
* Sub-task

If the appropriate type is unclear, classify based on intent:

* Existing behavior is broken → Bug
* User-facing capability or outcome → Story / New Feature / Improvement
* Technical work without direct user-observable behavior → Task
* Work too large for one sprint and containing child work → Epic
* Collection of Epics tied to a strategic goal → Initiative
* Research or uncertainty-reduction work → Spike
* Discovery-stage concept not yet committed → Idea
* Child unit of an existing work item → Sub-task

Do not force a Story format onto purely technical work.

### 2. Gather required context

Collect only what is relevant for the selected type.

Common fields:

* title
* problem/background
* scope
* expected outcome
* dependencies
* affected systems/components
* relevant configuration or feature flags
* supporting documentation
* acceptance criteria
* evidence

For Bugs also gather:

* environment
* deterministic reproduction steps
* actual behavior
* expected behavior
* severity
* priority
* workaround if known
* evidence such as screenshots, logs, traces, or API responses

Do not fabricate unknown values.

### 3. Draft acceptance criteria

For Story, New Feature, Improvement, and user-observable Tasks, follow:

`.agents/standards/given-when-then.md`

Acceptance criteria must:

* describe observable outcomes
* cover the intended happy path
* include important negative/error paths
* avoid vague words such as "correctly" or "properly"
* avoid prescribing implementation unless the implementation itself is the requirement

Small copy/UI changes may use an observable checklist instead of Given/When/Then.

### 4. Validate readiness

Use:

* `.agents/standards/invest.md`
* `.agents/standards/definition-of-ready.md`

For Story/New Feature/Improvement, apply INVEST.

For all ticket types, determine whether a contributor can begin without inventing critical information.

Produce one readiness verdict:

* READY
* NEEDS INFO
* BLOCKED

If the draft is not Ready, identify the specific gap.

Do not silently repair missing product requirements with agent assumptions.

### 5. Bug quality checks

For Bugs:

* reproduction steps must be deterministic
* actual and expected behavior must both be explicit
* severity and priority must be assessed separately using `.agents/standards/severity-vs-priority.md`
* environment must be identified
* relevant configuration should be recorded when known
* evidence should be included or referenced when available

If root cause is unknown, say unknown.

Do not convert a suspected root cause into a fact.

### 6. Synthesize Definition of Done

Use:

`.agents/standards/definition-of-done.md`

Tailor the DoD to this work item.

Do not paste every generic checklist item if it clearly does not apply.

### 7. Produce draft

The draft should be concise enough for humans to scan but complete enough to implement and test.

Recommended structure:

```markdown
# <Title>

## Background

<Why this work exists>

## Scope

<What is included>

## Out of Scope

<Optional — use when boundaries matter>

## Acceptance Criteria

<Given/When/Then scenarios or observable rules>

## Dependencies / Configuration

<Dependencies, feature flags, permissions, runtime modes>

## Evidence

<Relevant links, screenshots, traces, logs, or references>

## Definition of Done

<Tailored checklist>
```

For Bugs, use:

```markdown
# <Title>

## Environment

<Environment/configuration>

## Steps to Reproduce

1. ...
2. ...
3. ...

## Actual Behavior

...

## Expected Behavior

...

## Severity

...

## Priority

...

## Evidence

...

## Suspected Root Cause

<Optional; clearly label inference>

## Definition of Done

...
```

### 8. Review before outward action

Present the draft for review.

Allow focused revision of individual sections.

Do not perform an outward write simply because the user asked to "make a ticket" unless the current workflow explicitly supports external submission and the user separately authorizes it.

## Agent-assisted enrichment

When repository or project context is available, optionally enrich a draft with:

* related existing tests
* likely affected code areas
* related work items
* recent relevant implementation history
* canonical Wiki documentation
* existing working-memory context

Label agent-derived findings as such.

Do not present them as user-provided facts.

## Knowledge behavior

If this skill discovers durable requirements-writing or project knowledge:

1. record useful working context in memPalace-style memory
2. deduplicate
3. promote broadly useful validated knowledge to the GitHub Wiki
4. link the working-memory entry to the canonical Wiki page

Do not store ticket-specific confidential information in the public portfolio's example knowledge.

## Output quality bar

A good ticket should allow a new contributor to answer:

* Why are we doing this?
* What exactly is in scope?
* What observable behavior defines success?
* What dependencies/configuration matter?
* How will QA know it works?
* What makes the work Done?

If those answers cannot be derived, the ticket is not Ready.

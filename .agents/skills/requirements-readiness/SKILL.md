---

name: requirements-readiness
description: >
  Review an engineering work item for implementation readiness. Gather relevant
  repository and knowledge context, assess completeness and testability, synthesize
  a Definition of Done, identify conflicts or missing information, and return a
  READY / NEEDS INFO / BLOCKED verdict. Do not modify external systems by default.
---

# Requirements Readiness

## Purpose

Determine whether a work item contains enough verified information for engineering and QA to begin responsibly.

This skill reviews existing work. It does not silently rewrite unclear requirements into something more convenient.

Use the shared standards under `.agents/standards/`.

## Core rules

* Never invent missing requirements.
* Retrieve context before declaring information missing.
* Separate verified facts from inference.
* Prefer current code and canonical documentation over stale notes.
* Surface conflicts explicitly.
* Testability is a readiness requirement.
* Do not perform outward writes by default.
* A polished ticket can still be not Ready.
* A short ticket can still be Ready if its requirements are complete and testable.

## Flow

### 1. Read and classify the work item

Identify:

* work-item type
* affected product/system area
* stated objective
* acceptance criteria or expected behavior
* dependencies
* linked artifacts
* configuration or feature flags
* apparent implementation scope

Classify the work item as one of:

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
* Unknown

If classification is uncertain, say so.

### 2. Gather context

Before calling something missing, search the context available to this repository.

Inspect as relevant:

* current work-item text
* linked work items
* GitHub Wiki pages
* `knowledge/wiki-map.md`
* `knowledge/mempalace/`
* source code
* existing tests
* implementation/spec files
* recent related changes when available

Do not blindly crawl the entire repository.

Start from:

* names/components in the ticket
* linked files
* canonical Wiki index
* known files of record

### 3. Build a Sources of Record map

Produce a concise map such as:

```text
Work item:
- tickets/ready/ABC-123.md

Canonical shared docs:
- GitHub Wiki: Payments Architecture
- GitHub Wiki: Test Strategy

Code:
- services/payments/...
- apps/member/...

Tests:
- tests/api/payments/...
- tests/ui/payments/...

Working memory:
- knowledge/mempalace/payment-timeout-history.md
```

This map should be suitable for handing to downstream agents.

### 4. Run readiness checks

Use:

* `.agents/standards/definition-of-ready.md`
* `.agents/standards/invest.md` for Story/New Feature/Improvement
* `.agents/standards/given-when-then.md` for observable acceptance criteria
* `.agents/standards/severity-vs-priority.md` for Bugs

Assess:

* title clarity
* problem/context
* scope
* acceptance criteria / expected behavior
* testability
* dependencies
* sizing
* configuration
* evidence
* linked design/specs when relevant

### 5. Assess testability

Ask:

* Can at least one objective test be derived?
* Are expected outcomes observable?
* Is the starting state identifiable?
* Are important negative paths specified?
* Does configuration change expected behavior?
* Is there an authoritative read-back or evidence source?
* Is any required external dependency unavailable to QA/automation?

If the requirement cannot be verified objectively, explain why.

### 6. Synthesize a Definition of Done

Use:

`.agents/standards/definition-of-done.md`

Create a ticket-specific DoD.

Do not treat the synthesized DoD as an original requirement if it contains inferred process expectations.

Label inferred additions clearly.

### 7. Detect conflicts

Look for disagreement between:

* ticket and current code
* ticket and Wiki
* ticket and linked work items
* Wiki pages
* working memory and canonical docs
* acceptance criteria and implementation spec
* stated behavior and existing tests

For every material conflict, report:

* Source A
* Source B
* what conflicts
* which source currently appears stronger
* what still needs confirmation

Never silently reconcile conflicting requirements.

### 8. Assess scope and sizing

For Stories/New Features/Improvements, apply INVEST.

Flag likely oversizing when the work spans multiple independent capabilities or systems.

Do not assume that touching multiple repositories automatically means a ticket must be split; assess whether it still represents one coherent deliverable.

### 9. Produce the readiness verdict

Choose exactly one:

## READY

Use when:

* critical requirements are present or recoverable from verified context
* the work is objectively testable
* dependencies do not block beginning work
* scope is understandable
* no unresolved conflict prevents implementation

## NEEDS INFO

Use when:

* one or more critical requirements cannot be found
* expected behavior is ambiguous
* meaningful acceptance criteria cannot be derived
* material configuration is unknown
* a conflict needs product/engineering clarification

## BLOCKED

Use when:

* an explicit dependency prevents work
* required infrastructure/environment/access is unavailable
* another unresolved work item must complete first

Do not use BLOCKED simply because the ticket is poorly written. That is NEEDS INFO.

### 10. Produce the report

Use this structure:

```markdown
# Requirements Readiness: <work item>

## Verdict

READY | NEEDS INFO | BLOCKED

## Summary

<brief explanation>

## Sources of Record

<files/docs/tests inspected>

## Readiness Checks

- Title:
- Context:
- Scope:
- Acceptance Criteria:
- Testability:
- Dependencies:
- Configuration:
- Sizing:

## Synthesized Definition of Done

<ticket-specific DoD>

## Missing Information

<critical gaps or "None">

## Conflicts

<conflicts or "None identified">

## Candidate Tests

<small set of tests derivable from the requirement>

## Risks / Notes

<important context without turning speculation into fact>
```

## Bug-specific behavior

For Bugs, additionally verify:

* environment
* deterministic reproduction steps
* actual behavior
* expected behavior
* severity
* priority
* workaround if known
* evidence

If root cause is mentioned, determine whether it is:

* verified
* suspected
* unknown

Do not upgrade a suspected root cause to verified.

## Existing coverage check

When practical, inspect current tests and report:

* existing coverage that appears relevant
* obvious gaps
* whether existing tests actually exercise the stated requirement

Do not equate "a related test exists" with "the ticket is covered."

## Knowledge behavior

If the review discovers useful durable information:

* keep investigation-stage findings in memPalace-style working memory
* deduplicate before adding
* promote validated team-wide knowledge to the GitHub Wiki
* update `knowledge/wiki-map.md` when introducing a major canonical page
* preserve a pointer from working memory to the canonical page

## Outward actions

Default behavior is read-only.

Do not:

* edit the ticket
* comment on the ticket
* change labels/status
* create linked work
* modify external documentation

unless a higher-level workflow explicitly authorizes that action and the user has approved it.

## Quality bar

The review is successful when a downstream engineer can tell:

* what is known
* what is missing
* what is authoritative
* what conflicts
* what can be tested
* what would make the work Done
* whether implementation can responsibly begin

---

name: qa-ticket-intake
description: >
  Run QA intake on an implementation-ready work item. Gather relevant context,
  assess root cause when applicable, inspect existing coverage, identify sibling
  defects, determine QA testability and automation candidacy, and produce a
  structured test plan plus downstream handoff. Uses GitHub Wiki as canonical
  shared documentation and memPalace-style memory as optional working context.
---

# QA Ticket Intake

## Purpose

Act as the QA front door for a work item that is ready for validation.

This skill converts an implementation-ready ticket into a structured QA handoff by answering:

* What changed?
* What is the expected behavior?
* What risks matter?
* What existing coverage applies?
* What additional testing is needed?
* What can be automated?
* What requires human judgment?
* What evidence should be collected?
* What context should downstream agents inherit?

This skill does not execute the full test plan. It prepares it.

## Core rules

* Read before judging.
* Never invent missing requirements.
* Prefer verified context over memory.
* GitHub Wiki is the canonical shared knowledge layer.
* memPalace-style memory is operational context, not automatic truth.
* Current code and executable behavior must verify code-level claims.
* Existing tests must be inspected before proposing new automation.
* A related test is not automatically sufficient coverage.
* Separate facts, inference, and unknowns.
* Do not perform outward writes by default.
* Preserve a concise Sources of Record map for downstream agents.

## Inputs

Expected input:

* a work item / ticket
* repository/workspace context

Optional:

* pull request
* implementation spec
* linked issue history
* environment information
* existing test results

## Flow

### 0. Confirm readiness

If a `requirements-readiness` assessment exists, read it.

If not, perform a lightweight readiness check sufficient to establish:

* expected behavior is understandable
* acceptance criteria exist or can be verified from canonical sources
* the work is QA-testable

If critical requirements are missing, stop intake and return:

`NEEDS REQUIREMENTS CLARIFICATION`

Do not create a test plan from guessed requirements.

### 1. Classify the change

Record:

* issue type
* affected product/system area
* public-facing vs internal/client-facing surface
* UI / API / backend / integration / infrastructure / AI-system scope
* risk level
* likely test surfaces

Potential test surfaces include:

* unit
* API/service
* integration
* UI
* mobile
* accessibility
* AI evaluation
* observability
* data persistence/read-back
* release regression

### 2. Gather context

Inspect the minimum useful context.

Read as relevant:

* work item
* acceptance criteria
* linked work
* implementation spec
* GitHub Wiki pages from `knowledge/wiki-map.md`
* related memPalace entries
* changed source code
* existing tests
* relevant configuration/feature flags
* recent related changes if available

Do not perform a blind repository-wide crawl.

### 3. Produce a Sources of Record map

Capture the authoritative context downstream agents should use.

Example:

```text
Work item:
- tickets/ready/ABC-123.md

Canonical documentation:
- GitHub Wiki: Quote Lifecycle
- GitHub Wiki: Test Strategy

Implementation:
- services/quotes/...
- apps/customer/...

Existing tests:
- tests/api/quotes/...
- tests/ui/customer/...

Working memory:
- knowledge/mempalace/quote-timeout-history.md
```

### 4. Root-cause assessment

For Bugs:

Determine whether root cause is:

* VERIFIED
* SUSPECTED
* UNKNOWN

If no credible RCA exists, investigate the relevant implementation sufficiently to identify likely failure areas.

Do not claim certainty without evidence.

Record:

* observed symptom
* failure mechanism if known
* affected code path
* authoritative evidence
* confidence level

### 5. Sibling-defect scan

For Bugs with a known or suspected implementation pattern, search for the same root-cause pattern elsewhere.

Look for:

* duplicate unsafe logic
* same missing guard
* same incorrect assumption
* same API misuse
* same data-handling bug
* same validation omission

Search by root-cause pattern, not merely symptom text.

Return:

* location
* reason it may be related
* confidence

Do not automatically classify every similar-looking location as a defect.

### 6. Existing coverage assessment

Inspect relevant automated tests.

For each existing test, determine:

* what requirement it exercises
* which layer it covers
* whether it validates authoritative state
* whether it contains vacuous assertions
* whether required configuration paths are represented
* whether it would catch the reported regression

Classify coverage:

* STRONG
* PARTIAL
* ADJACENT
* NONE
* UNKNOWN

Do not use file/tag similarity alone as proof of coverage.

### 7. Unit/integration coverage judgment

Assess whether implementation-level coverage appears appropriate.

Do not confuse:

> tests ran

with:

> changed behavior is covered

Identify meaningful gaps without automatically requiring a new ticket.

### 8. QA testability

Determine whether QA can meaningfully validate the requirement.

Classify:

* TESTABLE
* PARTIALLY TESTABLE
* NOT TESTABLE
* UNKNOWN

Explain constraints.

Examples:

* unavailable external dependency
* hardware-only behavior
* unavailable environment
* missing authoritative read-back
* subjective-only requirement
* inaccessible third-party state

### 9. Automation candidacy

Classify each meaningful test step before splitting work.

Default to automation when the step is objective and performable by available tooling.

A step is a strong automation candidate when it has:

* deterministic setup
* objective outcome
* accessible interface
* stable read-back
* reproducible execution
* reasonable cost

A step may remain human when it requires:

* genuine subjective judgment
* inaccessible external state mutation
* physical/hardware interaction unavailable to the suite
* capability the automation environment cannot create or observe

A missing helper is not, by itself, a reason to classify a step as manual.

### 10. Configuration-path analysis

Identify settings, feature flags, model choices, permissions, or runtime modes that alter the behavior under test.

Separate:

* behavior-changing configuration
* setup-only configuration

Include relevant paths in the test plan.

Do not create combinatorial matrices for unrelated setup flags.

### 11. AI-system checks

If the ticket changes AI/LLM behavior, determine which evaluations are relevant:

* groundedness
* retrieval quality
* citation accuracy
* relevance
* instruction following
* tone
* harmful output
* prompt injection resistance
* regression dataset performance
* latency
* token/cost behavior

AI evaluation must be treated as part of the QA plan, not as an optional appendix.

### 12. Accessibility

For public-facing UI changes, include accessibility checks when applicable.

Consider:

* keyboard navigation
* focus order
* focus visibility
* semantic roles/names
* screen-reader behavior
* contrast
* error messaging
* dynamic-state announcements

### 13. Build the test plan

Every test step must identify:

* purpose
* precondition
* action
* expected result
* evidence/read-back
* automation classification

Recommended format:

```markdown
### TP-1 — <Scenario>

**Purpose:**  
...

**Precondition:**  
...

**Action:**  
...

**Expected:**  
...

**Evidence:**  
...

**Execution:** automated | human

**Reason:**  
...
```

Include:

* happy path
* negative paths
* regression checks
* configuration paths
* persistence/read-back
* accessibility when applicable
* AI evaluation when applicable

### 14. Existing automated tests to run

Identify tests that can provide immediate regression signal.

For each:

* test file
* scenario/test name
* tag/filter if applicable
* why it is relevant

Do not list tests solely because their name resembles the ticket.

### 15. Coverage gaps

Identify gaps by layer:

* unit
* integration
* API
* UI
* mobile
* accessibility
* AI evaluation
* observability
* release regression

For each gap, state whether it should become:

* immediate QA work
* durable automation
* implementation-level coverage
* human-only validation
* no action

### 16. Produce downstream handoff

Return a concise artifact containing:

```markdown
# QA Intake: <work item>

## Classification

...

## Sources of Record

...

## Root Cause

VERIFIED | SUSPECTED | UNKNOWN | N/A

...

## Sibling-Defect Findings

...

## Existing Coverage

...

## Coverage Gaps

...

## QA Testability

...

## Automation Candidacy

...

## Configuration Paths

...

## Test Plan

...

## Existing Automated Tests to Run

...

## AI Evaluation Requirements

...

## Accessibility Requirements

...

## Risks / Unknowns

...

## Recommended Next Step

...
```

## Human handoff rule

Do not give the human every check merely because a human exists.

The QA-agent workflow should automate objective work and reserve human attention for:

* subjective judgment
* inaccessible external actions
* final confidence/sign-off
* explicitly gated decisions

## Knowledge behavior

Before adding operational memory:

1. search for existing related entries
2. update rather than duplicate
3. keep findings distilled
4. include provenance
5. promote durable team knowledge to the GitHub Wiki
6. update `knowledge/wiki-map.md` when a major canonical page is added
7. leave a pointer from memPalace to the Wiki page

## Outward actions

Default behavior is read-only.

Do not automatically:

* modify the work item
* comment externally
* create follow-up tickets
* change labels/status
* merge code
* deploy

A higher-level orchestration skill may authorize these actions under its own human-gate rules.

## Quality bar

QA intake is complete when downstream agents and the human QA engineer can understand:

* what changed
* what evidence matters
* what already has coverage
* what still needs testing
* which checks can be automated
* which checks genuinely require a human
* what configuration alters expected behavior
* what risks or unknowns remain

---

name: release-testing
description: >
  Orchestrate release-level QA across multiple work items and test surfaces.
  Verify release freshness, derive scope from included changes, prioritize by
  impact and risk, execute independent checks concurrently where safe, triage
  failures, cross-check claimed coverage against actual exercised behavior,
  preserve manual-vs-automated test semantics, and produce a concise release
  confidence summary. Reuses failure-triage, knowledge-curation, and adversarial
  verification instead of duplicating their logic.
---

# Release Testing

## Purpose

Validate a release as a coherent system rather than treating it as a loose collection of individually tested tickets.

Release testing answers:

* Is the intended release actually deployed?
* What changed?
* Which user/system behaviors are most at risk?
* Which existing automated suites should run?
* What additional targeted testing is needed?
* Which failures are product, test, orchestration, or environment issues?
* Did the tests that passed actually cover the release changes they were mapped to?
* What remains unknown?
* Is there enough evidence for a human to make a release decision?

This skill orchestrates release-level work.

It should reuse lower-level skills rather than reimplementing their behavior.

## Core rules

* Verify release freshness before trusting test results.
* Scope from actual release contents, not assumptions.
* Prioritize by impact and risk.
* Reuse ticket-level QA context where available.
* Do not assume a passing test covers a mapped work item.
* Preserve raw evidence.
* Distinguish product failures from test/orchestration/environment failures.
* Do not overwrite manual test semantics with automated execution records.
* Parallelize only independent work.
* Human release confidence remains an explicit gate.

## Reused skills

Use:

* `.agents/skills/qa-ticket-intake/`
* `.agents/skills/failure-triage/`
* `.agents/skills/knowledge-curation/`

Use:

* `.agents/standards/adversarial-verification.md`

Do not duplicate those rules here unless release-level behavior differs.

## Model routing

Default orchestration tier: **high reasoning**

Release-level coordination often crosses multiple work items, test layers, and failure classes.

Use:

### High reasoning

For:

* release orchestration
* release-scope interpretation
* risk prioritization
* cross-ticket reasoning
* adversarial coverage review
* synthesis when evidence conflicts
* final release summary

### Standard

For:

* test-result parsing requiring judgment
* ticket-to-test mapping
* ordinary failure triage
* targeted QA analysis
* release impact analysis

### Economy

For:

* deterministic test execution
* structured extraction
* test-count parsing
* mechanical log collection
* simple file/report indexing

Escalate based on uncertainty, not job title alone.

## Inputs

Expected:

* release identifier, branch, tag, build, deployment, or release-candidate reference
* target environment
* repository/workspace access

Useful optional inputs:

* included work items
* fix version / milestone
* changelog
* deployment metadata
* commit range
* pull requests
* prior QA intake reports
* existing release test plan
* manual test cycle
* CI results

## Flow

### 1. Identify the release

Record:

* release identifier
* target environment
* branch/tag/commit/build identifier
* deployment timestamp when available
* included work-item source
* expected release scope

Do not proceed from a vague label like "latest" when an exact build can be established.

### 2. Freshness gate

Before executing release tests, verify that the intended build is actually present in the target environment.

Evidence may include:

* deployed commit SHA
* build/version endpoint
* deployment metadata
* artifact version
* container/image digest
* environment banner
* health/version response

Classify freshness:

* **FRESH**
* **STALE**
* **UNKNOWN**

If `STALE`, stop release validation against that environment.

Return:

`BLOCKED — intended release is not deployed`

If `UNKNOWN`, do not treat subsequent green tests as reliable release evidence without clearly flagging the uncertainty.

### 3. Derive release scope

Build scope from the strongest available evidence.

Potential sources:

* milestone/fixVersion
* merged PRs
* commit range
* release notes
* deployment artifact
* linked work items

Create a release scope table:

```text
Work item | Area | Change type | Risk | Existing QA intake
```

Do not include unrelated historical tickets merely because they mention the same feature.

### 4. Gather ticket-level context

For each meaningful included work item:

* reuse existing `qa-ticket-intake` output when available
* otherwise perform enough intake to understand:

  * expected behavior
  * affected surfaces
  * existing coverage
  * configuration paths
  * known risks

Avoid repeating broad discovery already completed at ticket level.

### 5. Build release impact map

Group changes into impacted areas.

Examples:

* authentication
* payments
* quote lifecycle
* mobile check-in
* AI retrieval
* model routing
* persistence
* notifications
* shared infrastructure

For each area record:

* included tickets
* shared dependencies
* integration boundaries
* high-risk configuration
* relevant automated suites
* human-only validation if any

### 6. Prioritize by release risk

Prioritize testing based on factors such as:

* customer impact
* breadth of shared dependency
* statefulness
* integration count
* production criticality
* regression history
* configuration complexity
* AI nondeterminism
* security/access impact
* architectural novelty

Suggested release risk:

* CRITICAL
* HIGH
* MEDIUM
* LOW

Risk determines rigor and ordering, not whether a requirement should be tested at all.

### 7. Build the execution plan

Construct a release-level plan containing:

* smoke checks
* targeted ticket validation
* impacted regression suites
* cross-feature integration checks
* configuration-path checks
* accessibility checks
* AI evaluations
* release-specific human checks

Separate:

* independent parallel work
* shared-state work that must serialize

### 8. Concurrency plan

Parallelize independent checks.

Good candidates:

* read-only API suites
* separate feature areas
* independent accessibility analysis
* independent AI evaluation batches
* static coverage analysis

Serialize when tests share mutable state such as:

* global feature flags
* one shared account
* destructive fixtures
* payment terminals
* shared hardware
* globally scoped configuration
* workflows that assume ordered lifecycle state

Do not optimize runtime at the cost of invalid evidence.

### 9. Execute automated checks

Use economy-tier execution agents when instructions are explicit.

Capture for every run:

* command
* suite/test
* environment
* build identifier
* configuration
* start/end result
* raw report location
* pass/fail/skip counts
* first meaningful failure

Do not ask the execution agent to perform complex failure interpretation unless needed.

### 10. Parse results separately from execution

Where practical, use a separate parser/analyst from the executor.

This reduces the chance that the same agent both caused and rationalized an orchestration error.

Mechanical parsing may use economy tier.

Interpretive parsing should use standard tier.

### 11. Triage failures

For meaningful failures, invoke:

`.agents/skills/failure-triage/`

Classify each:

* PRODUCT
* TEST
* ORCHESTRATION
* ENVIRONMENT
* UNKNOWN

Do not include orchestration failures in the product-defect count.

Do not silently rerun until green.

Preserve original failures and retry history.

### 12. Retry policy

Retry only when the retry provides diagnostic value or the suite has an established retry policy.

Record:

* original result
* retry result
* reason for retry
* whether the failure is reproducible

A passing retry does not erase the original failure.

Classify persistent flaky behavior separately in the release summary.

### 13. Coverage cross-check

After execution, verify that mapped release work was actually exercised.

For each included work item ask:

* Which test or QA step claims to cover it?
* What behavior did that test actually exercise?
* Did it execute the relevant configuration path?
* Did it validate the acceptance criterion?
* Did it observe authoritative state?
* Would it have failed if the release change were broken?

Classify ticket coverage:

* **CONFIRMED**
* **PARTIAL**
* **ADJACENT**
* **UNMAPPED**
* **UNKNOWN**

A passing suite can still leave a ticket `UNMAPPED`.

### 14. Adversarial release review

Dispatch the Adversarial Verifier for high-risk releases.

Ask:

* Which "green" results are least trustworthy?
* Which tickets are only nominally covered?
* Are any assertions vacuous?
* Are important feature-flag paths missing?
* Did the deployment freshness check prove the correct artifact?
* Did shared-state contention invalidate any runs?
* Were retries hiding regressions?
* Are there release risks not represented by the ticket list?
* Did AI evaluations use the intended model/configuration/dataset?

The goal is to challenge release confidence before the human does.

### 15. Manual test-cycle reconciliation

If the organization tracks manual test cases separately from automation, preserve that distinction.

Do not record an automated execution as though a human manually performed the test unless the tracking system explicitly models automated execution that way.

Instead report:

* manual cases completed by a human
* automated checks executed by the system
* overlapping coverage
* uncovered manual-only areas

Automation evidence may support release confidence without falsifying manual execution history.

### 16. Release-specific AI checks

If AI behavior changed, confirm:

* intended model/provider
* intended routing tier
* expected prompt/instruction version
* retrieval/index version where relevant
* evaluation dataset/version
* thresholds
* latency/cost limits

Run relevant evaluations such as:

* groundedness
* retrieval relevance
* citation correctness
* instruction following
* safety
* prompt injection resistance
* regression-set accuracy
* latency
* token/cost behavior

Do not rely on a handful of anecdotal prompts for a meaningful AI release.

### 17. Observability checks

For high-impact backend/integration/AI releases, inspect appropriate observability signals where access exists.

Examples:

* error-rate change
* warning spikes
* latency regressions
* failed jobs
* queue backlog
* model timeout rate
* token-cost anomalies
* retrieval failures

Treat telemetry as supporting evidence, not a replacement for requirement testing.

### 18. Release findings ledger

Maintain a ledger of meaningful findings.

Each finding must have:

* ID
* source
* classification
* severity/risk
* owner/status if applicable
* evidence
* resolution/disposition

Allowed dispositions:

* RESOLVED
* ACCEPTED RISK
* FOLLOW-UP
* BLOCKER
* UNKNOWN
* HUMAN DECISION

Do not allow meaningful findings to disappear inside a long test log.

### 19. Determine release confidence

Do not let the system silently make the final release decision.

Produce a confidence assessment:

* **HIGH**
* **MEDIUM**
* **LOW**
* **INSUFFICIENT EVIDENCE**

Consider:

* freshness
* test execution
* coverage mapping
* unresolved product defects
* environment validity
* flaky/unknown failures
* human-only work outstanding
* adversarial verifier concerns
* AI evaluation outcome where relevant

This is evidence for the human release gate, not an autonomous production approval.

### 20. Human release gate

Present:

* release identity
* freshness result
* scope tested
* pass/fail summary
* product defects
* test/orchestration/environment failures
* ticket coverage map
* human checks remaining
* known risks
* adversarial concerns
* confidence assessment

Require explicit human authorization before any gated release/deploy/publish action.

## Output

Use:

```markdown
# Release Test Summary: <release>

## Release Identity

- Release:
- Build/commit:
- Environment:
- Freshness: FRESH | STALE | UNKNOWN

## Scope

<included work items and impacted areas>

## Risk Summary

<critical/high-risk areas>

## Execution Summary

- Automated:
- Human:
- Blocked:
- Skipped:

## Test Results

<key suite results>

## Failure Classification

### Product
...

### Test
...

### Orchestration
...

### Environment
...

### Unknown
...

## Ticket Coverage

| Work Item | Coverage | Evidence | Notes |
|---|---|---|---|

## AI Evaluation

<if applicable>

## Accessibility

<if applicable>

## Observability

<if applicable>

## Open Findings

<ledger of unresolved items>

## Adversarial Review

<concerns or "No material concerns identified">

## Human Checks Remaining

...

## Release Confidence

HIGH | MEDIUM | LOW | INSUFFICIENT EVIDENCE

## Release Gate

AWAITING HUMAN DECISION
```

## Release blocker guidance

Typical blockers include:

* intended build not deployed
* critical product defect
* invalid test environment
* critical ticket with no meaningful coverage
* required human validation incomplete
* unresolved high-confidence security/data-integrity concern

Do not automatically block a release for:

* unrelated test infrastructure issue
* known accepted flaky test
* documentation typo
* low-risk uncovered area explicitly accepted by the human

Surface the evidence and risk instead.

## Knowledge closeout

After the human release decision, invoke:

`.agents/skills/knowledge-curation/`

Candidate knowledge includes:

* newly discovered regression patterns
* stable configuration behavior
* release-specific operational constraints
* useful failure signatures
* new canonical testing guidance
* AI evaluation/routing findings

Do not promote one-off release noise into permanent documentation.

## Release metrics

When available, record metrics useful for improving the system:

* release test duration
* parallelization efficiency
* tests executed
* ticket coverage percentage
* confirmed vs adjacent coverage
* product defect count
* orchestration failure count
* environment failure count
* flaky retry rate
* time/token/cost by agent role
* escalation count
* verifier rejection

---

name: qa-agent-team
description: >
  Orchestrate a role-based QA agent team around a human QA engineer. Supports
  ticket-level QA execution and test-automation implementation. Uses specialized
  agents for intake, architecture, implementation, execution, adversarial
  verification, accessibility, failure analysis, and knowledge curation.
  Preserves explicit human gates for design and release decisions and routes work
  to the least-expensive model tier that can reliably perform each role.
---

# QA Agent Team

## Purpose

Coordinate specialized QA agents around a single work item while keeping human attention focused on the highest-value judgment points.

This skill is an orchestrator.

It does not perform all testing or implementation itself. It delegates work, controls handoffs, enforces gates, routes work to appropriate model tiers, and synthesizes results.

## Core principle

Agents can fail in correlated ways.

A second agent reviewing the first agent is useful, but it may share the same blind spot.

Use human attention where independence matters most:

* design approval for high-risk or novel automation
* final release/outward-action approval
* subjective QA judgment
* unresolved ambiguity
* explicit final confidence/sign-off

Automate objective, repeatable work wherever practical.

## Model routing policy

Use the least-expensive model that can reliably perform the assigned role.

Model choice should be based on task complexity, ambiguity, risk, and required judgment rather than assigning every agent the strongest available model.

### High-reasoning tier

Use for:

* orchestration
* architecture
* adversarial verification
* complex failure analysis
* high-risk design decisions
* conflicting evidence
* cross-system reasoning
* ambiguous requirements
* final synthesis when multiple agent outputs disagree

Typical roles:

* Orchestrator
* Architect
* Adversarial Verifier
* Failure Triage Analyst when root cause or classification is complex

### Standard tier

Use for:

* implementation
* QA intake
* requirements analysis
* release parsing
* accessibility analysis
* ordinary failure triage
* test-plan generation
* coverage assessment

Typical roles:

* Implementer
* Intake Analyst
* Requirements Analyst
* Accessibility Specialist
* Release Parser
* Failure Triage Analyst for routine cases

### Economy tier

Use for:

* deterministic test execution
* structured extraction
* log/tally parsing with explicit rules
* summarization
* knowledge deduplication
* Wiki-map maintenance
* file/index maintenance
* mechanical evidence collection

Typical roles:

* Test Executor
* Knowledge Curator
* lightweight parser/extractor agents

### Escalation rule

Do not keep a task on a cheaper model merely to reduce cost.

Escalate to a stronger tier when:

* evidence conflicts
* confidence is low
* failure classification is uncertain
* requirements are ambiguous
* the task crosses multiple subsystems
* the current model cannot establish authoritative evidence
* the task requires meaningful architectural judgment
* an unexpected result falls outside the agent's explicit operating rules

An agent may recommend escalation rather than forcing a conclusion.

### De-escalation rule

Do not use a high-reasoning model for work that has become mechanical.

Once a design, test plan, or decision has reduced a task to explicit steps, hand the work to a lower-cost execution agent where practical.

Example:

```text
Architect (high reasoning)
        ↓
Approved test design
        ↓
Test Executor (economy)
        ↓
Raw evidence
        ↓
Adversarial Verifier (high reasoning)
```

### Routing objective

Optimize for:

1. correctness
2. reliability
3. evidence quality
4. latency
5. token and monetary cost

Cost optimization must not override correctness or required human gates.

### Routing observability

Record model-routing metadata when the platform supports it:

* agent role
* model/tier used
* task type
* token usage
* latency
* escalation/de-escalation events
* final verifier outcome

This data may later be used to evaluate whether a lower-cost model is reliable enough for a given role.

### Routing evaluation

Treat model routing itself as an AI-system behavior that can be evaluated.

Useful metrics include:

* success rate by role/model
* verifier rejection rate
* escalation frequency
* average tokens per completed task
* latency per role
* cost per successful workflow
* rate of false PRODUCT / TEST / ORCHESTRATION classifications
* percentage of economy-tier outputs accepted without correction

Prefer evidence-based routing decisions over assumptions that a larger model is always necessary.

## Supported modes

### `qa`

Run a work item through QA validation.

Typical flow:

```text
QA Intake
   ↓
Step Classification
   ↓
Execution
   ↓
Adversarial Verification
   ↓
Failure / Defect Analysis
   ↓
Human Sign-off
   ↓
Knowledge Closeout
```

### `automate`

Implement durable test automation.

Typical flow:

```text
Architecture
   ↓
Adversarial Design Critique
   ↓
Human Design Gate
   ↓
Implementation
   ↓
Adversarial Verification
   ↓
Validation
   ↓
Human Release Gate
   ↓
Knowledge Closeout
```

## Team roster

### Intake Analyst

Uses:

`.agents/skills/qa-ticket-intake/`

Owns:

* context gathering
* coverage assessment
* testability
* automation candidacy
* test plan
* Sources of Record handoff

Default model tier: **standard**

### Architect

Owns:

* automation/system design
* test-layer selection
* reuse analysis
* configuration-path design
* evidence strategy
* Files of Record handoff

Default model tier: **high reasoning**

### Implementer

Owns:

* implementation of the approved design
* tests
* fixtures
* instrumentation required by the approved scope
* documentation updates

Does not redesign the task silently.

Default model tier: **standard**

Escalate when implementation requires unresolved architectural decisions.

### Test Executor

Owns:

* objective execution of the test plan
* UI/API/integration checks
* evidence capture
* configuration-path execution
* existing regression tests
* raw result reporting

Does not decide whether its own result is trustworthy.

Default model tier: **economy**

Escalate only when execution itself requires nontrivial interpretation.

### Adversarial Verifier

Owns:

* refuting designs
* refuting test results
* detecting vacuous greens
* checking authoritative read-back
* acceptance-criteria conformance
* configuration-path completeness
* mutation-verification evidence
* distinguishing product/test/orchestration failures

Use:

`.agents/standards/adversarial-verification.md`

Default model tier: **high reasoning**

### Failure Triage Analyst

Owns:

* product vs test vs orchestration vs environment classification
* root-cause evidence
* first meaningful error
* reproducibility
* likely affected subsystem

Default model tier: **standard**

Escalate to **high reasoning** when:

* evidence conflicts
* classification is uncertain
* the failure crosses subsystems
* root cause requires architectural reasoning

### Accessibility Specialist

Engage when the affected surface is public-facing or accessibility is otherwise in scope.

Owns:

* keyboard behavior
* semantic structure
* focus behavior
* screen-reader concerns
* contrast/error-state considerations
* accessibility-specific automation/evaluation

Default model tier: **standard**

### Knowledge Curator

Owns:

* deduplication
* memPalace hygiene
* promotion recommendations
* GitHub Wiki updates when authorized
* canonical pointers
* stale-knowledge detection

Default model tier: **economy**

Escalate when conflicting canonical sources require judgment.

### Requirements Analyst

Owns:

* requirements completeness
* readiness assessment
* acceptance-criteria quality
* Definition of Done synthesis
* requirement conflict detection

Uses:

`.agents/skills/requirements-readiness/`

Default model tier: **standard**

### Release Parser

Owns:

* structured interpretation of test-run evidence
* pass/fail tally extraction
* first meaningful failure extraction
* structured failure-evidence extraction for downstream triage
* coverage cross-checks

Default model tier: **standard**

Mechanical extraction may be delegated to an **economy** parser before interpretation.

## Shared operating protocol

Every dispatched agent must:

1. Read the current work item.
2. Read relevant acceptance criteria.
3. Read the nearest applicable `AGENTS.md`.
4. Use the Sources/Files of Record handoff if one exists.
5. Verify code-level claims against current code.
6. Separate fact, inference, and unknown.
7. Preserve evidence.
8. Avoid inventing missing information.
9. Avoid duplicating knowledge.
10. Report uncertainty instead of hiding it.

## Context-gathering rule

The front-door agent performs the broad gather.

Downstream agents should not repeat the entire discovery process unless:

* the handoff is incomplete
* the ticket changed
* evidence conflicts
* the agent needs a source not listed in the handoff

This reduces repeated retrieval, token usage, and context drift.

## Human gates

### Design-review gate

Required for:

* novel test architecture
* new AI evaluation architecture
* cross-cutting framework changes
* high-risk shared infrastructure
* security-sensitive work
* expensive external behavior
* unclear tradeoffs

Flow:

1. Architect produces design.
2. Adversarial Verifier produces critique.
3. Present both to the human.
4. Do not implement until approved.

### Release / outward-action gate

Explicit human approval is required before a workflow performs a gated outward action such as:

* merge
* deploy
* publish
* destructive change
* external submission where the current workflow marks approval as required

A goal such as "get this merged" is not itself authorization.

## Mode `qa`

### Step 1 — Intake

Run `qa-ticket-intake`.

Capture:

* classification
* Sources of Record
* root cause
* existing coverage
* coverage gaps
* testability
* automation candidacy
* configuration paths
* test plan
* existing tests to run
* accessibility/AI-evaluation requirements

Default model tier: **standard**

### Step 2 — Classify every test-plan step

Before assigning work, label each test step:

* `AUTOMATED/AGENT`
* `HUMAN`
* `BLOCKED`
* `UNKNOWN`

Default objective, tool-accessible checks to `AUTOMATED/AGENT`.

Use `HUMAN` only when the step genuinely requires:

* subjective judgment
* unavailable physical interaction
* inaccessible external state mutation
* explicit human sign-off

A missing committed helper is not enough to classify a check as human.

### Step 3 — Present the split

Give the human:

* agent-executed checks
* human checks
* blocked/unknown checks
* relevant existing automated tests
* important risk areas

The human should not have to repeat objective checks simply because they are the QA owner.

### Step 4 — Execute

Dispatch the Test Executor.

Default model tier: **economy**

Run:

* objective test-plan steps
* relevant existing regression tests
* configuration paths
* accessibility automation where applicable
* AI evaluations where applicable

Capture raw evidence.

Escalate interpretation rather than upgrading the executor unnecessarily.

### Step 5 — Verify

Dispatch the Adversarial Verifier.

Default model tier: **high reasoning**

The verifier must ask:

* Was the correct thing tested?
* Was authoritative state observed?
* Could this result pass vacuously?
* Did the test cover the acceptance criterion?
* Did configuration alter the meaning?
* Did a workaround narrow the test?
* Is failure classification correct?

### Step 6 — Triage failures

For each failure, dispatch Failure Triage when needed.

Default model tier: **standard**

Escalate to **high reasoning** when classification is uncertain.

Classify:

* PRODUCT
* TEST
* ORCHESTRATION
* ENVIRONMENT
* UNKNOWN

Do not report an orchestration failure as a product defect.

### Step 7 — Defect output

When a confirmed product defect exists, produce a concise defect artifact containing:

* environment
* deterministic reproduction
* actual behavior
* expected behavior
* evidence
* severity
* priority
* root-cause status
* related/sibling findings where relevant

Do not automatically submit externally unless the active workflow authorizes it.

### Step 8 — Human sign-off

Present:

* what passed
* what failed
* what remains human-only
* unresolved unknowns
* verifier concerns
* confirmed product defects
* coverage gaps

The human owns final QA confidence.

### Step 9 — Knowledge closeout

Dispatch the Knowledge Curator.

Default model tier: **economy**

Record:

* durable operational findings
* newly discovered risks
* useful test heuristics
* canonical documentation pointers

Promote validated team-wide knowledge to the GitHub Wiki when authorized.

Escalate only when knowledge sources conflict or promotion requires nontrivial judgment.

## Mode `automate`

### Step 1 — Design

Dispatch Architect.

Default model tier: **high reasoning**

The design must include:

* requirement(s) being guarded
* target test layer(s)
* existing abstractions to reuse
* new abstractions only if necessary
* fixture/setup strategy
* authoritative evidence/read-back
* configuration paths
* cleanup/isolation
* mutation-verification plan
* files expected to change
* Files of Record

### Step 2 — Adversarial design critique

For full-risk work, dispatch the Adversarial Verifier.

Default model tier: **high reasoning**

Ask it to identify the strongest reasons the design could produce a confidently green but incorrect test.

### Step 3 — Human design gate

Present:

* design
* critique
* unresolved tradeoffs

Wait for explicit approval before implementation when this gate is required.

### Step 4 — Implement

Dispatch Implementer with:

* approved design
* Files of Record
* scoped instructions
* applicable `AGENTS.md`

Default model tier: **standard**

The Implementer should open the specified files directly rather than rediscovering the repository.

Escalate architectural questions instead of silently redesigning.

### Step 5 — Verify implementation

Dispatch Adversarial Verifier.

Default model tier: **high reasoning**

Verify:

* acceptance-criteria conformance
* authoritative assertions
* deterministic fixtures
* no vacuous paths
* configuration-path coverage
* cleanup/restoration
* reuse-before-writing
* mutation verification
* documentation synchronization

### Step 6 — Validate

Use the least-expensive agent capable of executing the approved validation plan.

Default execution tier: **economy**

Run scope-appropriate tests.

Do not rely only on compilation or unit tests when the target behavior requires integration/UI/AI evidence.

Capture:

* command
* environment
* result
* relevant raw evidence
* failures
* mutation-verification result

Use a stronger model only for interpretation, not mechanical execution.

### Step 7 — Failure triage

Classify any failure before changing code to make the suite green.

Default tier: **standard**

Escalate uncertain or cross-system cases to **high reasoning**.

A failing new test may indicate:

* a real product regression
* wrong test design
* bad fixture
* environment issue
* orchestration error

Do not assume the test is wrong.

### Step 8 — Human release gate

Present:

* implementation summary
* validation result
* verifier verdict
* remaining risks
* unresolved failures

Require explicit approval before any gated merge/publish/deploy action.

### Step 9 — Close out

Dispatch Knowledge Curator where useful.

Default tier: **economy**

Update:

* test documentation
* working memory
* canonical Wiki where authorized
* architecture/knowledge maps if structure changed

## Risk-based rigor

Use a full pipeline for:

* novel work
* cross-cutting changes
* AI evaluation architecture
* shared test infrastructure
* integrations
* stateful workflows
* security-sensitive behavior
* high-impact releases

A lighter path may combine critique/review stages for routine low-risk work.

Never remove required human gates solely for speed.

## Concurrency

Parallelize independent agents when it reduces latency.

Do not parallelize tests that mutate the same shared state if concurrency could invalidate results.

Suitable parallel work may include:

* independent context research
* accessibility analysis
* static test-coverage review
* separate read-only test surfaces

Serialize:

* shared configuration mutations
* destructive test data
* stateful workflows sharing the same fixture/environment
* release checks known to contend

## Evidence rule

Agents return evidence, not just verdicts.

A useful execution result includes:

* what ran
* against what environment/configuration
* expected behavior
* observed behavior
* authoritative read-back
* raw failure evidence when relevant
* classification
* confidence
* model tier used where routing metadata is available

## No orphaned findings

Before finalizing a workflow, account for every meaningful finding.

Each finding must be:

* resolved
* explicitly accepted
* converted into follow-up work
* documented as an unknown
* intentionally dropped by human decision

Do not bury findings inside another artifact where they cannot be tracked.

## Knowledge architecture

Use:

* GitHub Wiki for canonical shared knowledge
* memPalace-style memory for working/operational knowledge
* `knowledge/wiki-map.md` as the lightweight canonical index

When knowledge is promoted:

1. validate
2. deduplicate
3. publish/update canonical Wiki page when authorized
4. update wiki map if needed
5. replace duplicate memPalace detail with a pointer

## Routing telemetry

When supported, the orchestrator should record per-agent routing information.

Recommended record:

```yaml
role: Test Executor
tier: economy
task: Run quote API regression checks
tokens_in: 0
tokens_out: 0
latency_ms: 0
escalated: false
verifier_result: SUPPORTED
```

Exact model names are optional.

The architecture should primarily depend on tiers/capabilities rather than vendor-specific model identifiers.

This keeps routing portable across model providers and future model changes.

## Routing feedback loop

Model routing should improve over time.

Periodically analyze routing telemetry for patterns such as:

* economy agents frequently escalating on one task class
* standard agents receiving high verifier rejection rates
* high-reasoning agents being used for mechanical work
* specific tasks consuming excessive context
* repeated handoff failures
* poor quality despite high model cost

Use those findings to adjust role defaults.

Example:

```text
Knowledge Curator
economy tier
↓
96% accepted without correction
↓
keep economy default
```

```text
Failure Triage
standard tier
↓
35% escalated on distributed-system failures
↓
route distributed-system triage directly to high reasoning
```

## Quality bar

This orchestration succeeds when:

* agents have clear responsibilities
* context is gathered once and handed forward
* objective QA work is automated
* model cost is matched to task complexity
* weaker models can escalate instead of hallucinating certainty
* stronger models are not wasted on mechanical work
* human judgment is used intentionally
* tests prove behavior rather than merely go green
* failures are correctly classified
* evidence survives handoffs
* knowledge improves after each workflow
* routing decisions become measurable over time
* outward actions remain governed

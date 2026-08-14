---

name: failure-triage
description: >
  Analyze a failed test, evaluation, workflow, or agent execution and determine
  whether the failure is caused by the product, the test, orchestration,
  environment, or insufficient evidence. Extract the first meaningful failure,
  preserve raw evidence, assess reproducibility and root cause, and produce a
  structured triage handoff. Escalate ambiguous or cross-system failures to a
  higher-reasoning model rather than forcing a conclusion.
---

# Failure Triage

## Purpose

Determine what actually failed before anyone changes code merely to make a test green.

This skill analyzes failures produced by:

* UI automation
* API/service tests
* integration tests
* mobile tests
* AI evaluations
* release runs
* agent workflows
* CI/CD execution
* orchestration infrastructure

The goal is not simply to explain an error message.

The goal is to classify the failure using evidence and identify the next responsible action.

## Core rules

* Preserve raw evidence before interpreting it.
* Find the first meaningful failure, not merely the final cascade.
* Distinguish execution failure from product failure.
* Do not assume a failing new test means the test is wrong.
* Do not assume a green retry means the original failure is irrelevant.
* Do not classify UNKNOWN evidence as PRODUCT.
* Verify code-level claims against current code.
* Verify expected behavior against acceptance criteria or canonical documentation.
* Separate observed facts, hypotheses, and unknowns.
* Escalate when evidence is contradictory or insufficient.

## Model routing

Default tier: **standard**

Use the standard tier for routine failure analysis with clear evidence.

Escalate to **high reasoning** when:

* multiple systems are involved
* evidence conflicts
* root cause crosses architectural boundaries
* a distributed/stateful failure is involved
* failure classification remains uncertain
* AI evaluation results disagree
* product and test behavior are both plausible explanations
* a shared-state or concurrency interaction is suspected

Mechanical evidence extraction may be delegated to an **economy** agent.

## Failure classes

Every analyzed failure receives exactly one primary classification:

### PRODUCT

The application or system violates an expected requirement.

Examples:

* API persists an incorrect value
* UI displays state inconsistent with authoritative read-back
* required workflow cannot complete
* AI output violates an explicit evaluation criterion
* feature behaves incorrectly under a documented configuration

### TEST

The automation or evaluation itself is incorrect.

Examples:

* wrong locator
* incorrect expected value
* bad fixture
* stale test data
* assertion observes the wrong object
* test assumes unsupported ordering
* evaluation rubric does not reflect the actual requirement

### ORCHESTRATION

The intended test never meaningfully executed because the runner/workflow failed.

Examples:

* wrong working directory
* missing executable
* malformed command
* parser failed to find results
* agent invoked the wrong tool
* test process never started
* pipeline masked the real command result

### ENVIRONMENT

The target environment is invalid or unavailable for the intended validation.

Examples:

* service unavailable
* staging deploy incomplete
* dependency inaccessible
* corrupted shared environment
* credentials/access unavailable
* required feature/configuration missing from target environment

### UNKNOWN

Available evidence does not support a responsible classification.

UNKNOWN is a valid result.

Do not manufacture certainty.

## Confidence

Every classification must include:

* **HIGH**
* **MEDIUM**
* **LOW**

Confidence describes evidence strength, not severity.

## Flow

### 1. Gather failure artifacts

Collect the available evidence.

Depending on the test system, this may include:

* raw terminal output
* structured test report
* stack trace
* screenshot
* trace
* network log
* API response
* persisted-state read-back
* AI prompt/output
* retrieved context
* evaluation result
* orchestration metadata
* environment/configuration
* source code
* test source
* acceptance criteria

Do not begin with a conclusion.

### 2. Confirm meaningful execution occurred

Before calling something a test failure, establish that the intended validation actually ran.

Look for evidence such as:

* scenario/test started
* expected application endpoint was contacted
* browser interaction occurred
* evaluation input was processed
* runner produced a normal result structure
* test framework produced a legitimate final status

If execution never reached the test behavior, strongly consider:

`ORCHESTRATION`

or:

`ENVIRONMENT`

rather than PRODUCT/TEST.

### 3. Preserve the raw failure

Record the original failure before summarizing it.

Examples:

```text
Observed HTTP status: 500
Expected: 200
Endpoint: POST /api/orders
```

or:

```text
Evaluation:
groundedness = 0.31
required threshold = 0.80
```

Do not overwrite raw evidence with an agent paraphrase.

### 4. Find the first meaningful error

Many failures cascade.

Example:

```text
1. Create-order request fails
2. order.id is undefined
3. UI search fails
4. cleanup fails
```

The meaningful failure is step 1.

Do not report step 3 as the root failure.

Identify:

* first meaningful error
* downstream/cascade errors
* unrelated cleanup errors

### 5. Establish expected behavior

Use the source-of-truth hierarchy from the root `AGENTS.md`.

Inspect:

1. current executable behavior/code where appropriate
2. GitHub Wiki canonical documentation
3. acceptance criteria / implementation spec
4. validated operational memory

If expected behavior itself is ambiguous, classify the result as UNKNOWN or escalate.

Do not invent expected behavior from the test assertion alone.

### 6. Check authoritative read-back

When the failure concerns persisted or stateful behavior, determine whether authoritative state can be read.

Examples:

* API GET after mutation
* database read through an approved interface
* emitted event
* persisted object state
* application-level status endpoint
* retriever result set
* evaluation dataset output

Prefer authoritative state over:

* toast message
* visual assumption
* cached object
* test-local state
* model-generated explanation

### 7. Inspect the test

Ask:

* Does it test the stated acceptance criterion?
* Is the expected value correct?
* Is setup deterministic?
* Does it depend on ambient environment data?
* Could it pass vacuously?
* Is the assertion reading the right object?
* Is configuration represented correctly?
* Is cleanup/isolation correct?
* Is stale state being reused?
* Is the failure caused by an unstable selector/wait?
* Did a previous scenario contaminate state?

### 8. Inspect the implementation

If PRODUCT remains plausible, inspect relevant implementation paths.

Look for:

* missing guards
* incorrect branching
* serialization/mapping mistakes
* stale cache/state
* error swallowing
* incomplete persistence
* race conditions
* permission/configuration errors
* wrong feature-flag path
* shared-state leakage

Do not broaden into an entire codebase audit unless evidence justifies it.

### 9. Check configuration

Record configuration that affects the behavior.

Examples:

* feature flags
* permissions
* model/provider choice
* environment variables
* runtime mode
* locale
* browser/device
* tenant/account settings
* test dataset version

Ask:

> Would this outcome be correct under a different configuration path?

Do not file a defect when the observed behavior matches the active configuration.

### 10. Assess reproducibility

Classify reproducibility:

* **CONSISTENT**
* **INTERMITTENT**
* **NOT REPRODUCED**
* **NOT RETRIED**
* **UNKNOWN**

Do not blindly rerun solely to make a failure disappear.

A retry may be useful diagnostically, but preserve the original failure.

If retries exist automatically, inspect all attempts.

### 11. AI-specific triage

For AI/LLM failures, additionally inspect:

* exact prompt/input
* system/developer instructions
* retrieved chunks/context
* retrieval scores
* model/provider/version
* temperature or generation settings when available
* evaluation rubric
* reference answer/data
* citations
* safety filters
* latency/token/cost information

Distinguish:

#### AI PRODUCT failure

The AI system behaves outside an explicit requirement.

#### AI EVALUATION failure

The evaluator/rubric is incorrect or unstable.

#### RETRIEVAL failure

Relevant context was not retrieved or ranked appropriately.

#### ORCHESTRATION failure

The model/evaluation pipeline did not run correctly.

Use the primary global class plus a subtype when useful.

Example:

```text
Primary: PRODUCT
Subtype: RETRIEVAL
```

### 12. Determine root-cause status

Root cause must be one of:

* **VERIFIED**
* **PROBABLE**
* **SUSPECTED**
* **UNKNOWN**

#### VERIFIED

Direct evidence demonstrates the mechanism.

#### PROBABLE

Evidence strongly supports one explanation but does not fully prove it.

#### SUSPECTED

Plausible hypothesis requiring additional investigation.

#### UNKNOWN

No responsible hypothesis is available.

Do not label a suspected code location as verified root cause.

### 13. Decide next action

Map classification to an appropriate next step.

#### PRODUCT

Recommend:

* defect artifact
* regression guard
* sibling-defect scan where relevant
* product fix investigation

#### TEST

Recommend:

* test/evaluation correction
* fixture repair
* assertion/read-back correction
* stability improvement
* mutation verification where relevant

#### ORCHESTRATION

Recommend:

* runner/workflow correction
* command/path/tooling repair
* parser correction
* rerun after orchestration is fixed

Do not count the failed attempt as product validation.

#### ENVIRONMENT

Recommend:

* repair/refresh environment
* validate deployment/configuration
* restore dependency/access
* rerun once environment is valid

#### UNKNOWN

Recommend the smallest next diagnostic action that could distinguish likely explanations.

## Output

Produce:

```markdown
# Failure Triage

## Classification

PRODUCT | TEST | ORCHESTRATION | ENVIRONMENT | UNKNOWN

**Confidence:** HIGH | MEDIUM | LOW

## Summary

<short factual explanation>

## First Meaningful Failure

<raw/structured evidence>

## Cascade Failures

<any downstream errors or "None identified">

## Expected Behavior Source

<acceptance criteria, Wiki, implementation spec, etc.>

## Authoritative Read-back

<what state/evidence says>

## Environment / Configuration

<relevant configuration>

## Reproducibility

CONSISTENT | INTERMITTENT | NOT REPRODUCED | NOT RETRIED | UNKNOWN

## Root Cause

VERIFIED | PROBABLE | SUSPECTED | UNKNOWN

<explanation and evidence>

## Test Assessment

<is the test/evaluator itself sound?>

## Product Assessment

<evidence for/against product failure>

## Recommended Next Action

<smallest responsible next action>

## Evidence

<files, logs, screenshots, traces, API responses, test reports>

## Unknowns

<remaining uncertainty>
```

## Defect readiness

Do not recommend filing a product defect unless there is sufficient evidence to describe:

* environment
* reproduction or triggering condition
* actual behavior
* expected behavior
* supporting evidence

Root cause is helpful but is not required to report a valid product defect.

## Sibling scan trigger

Recommend a sibling-defect scan when:

* root cause involves a reusable pattern
* the same helper/library is widely used
* the bug arises from a systemic missing guard
* similar code exists across components

Do not sibling-scan every one-off failure.

## Mutation verification trigger

If triage concludes a regression guard is needed, recommend mutation verification so the new test is shown to fail against the targeted regression.

## Knowledge behavior

If triage produces durable operational knowledge:

1. record a distilled finding in memPalace-style working memory
2. preserve evidence/provenance
3. deduplicate
4. promote stable, broadly useful findings to the GitHub Wiki when authorized
5. leave a pointer from working memory to the canonical Wiki page

Do not store entire raw logs as memory.

## Model escalation

Escalate to high reasoning rather than forcing classification when:

* PRODUCT and TEST remain equally plausible
* evidence sources contradict
* a distributed race is suspected
* an AI evaluation result cannot be distinguished from evaluator failure
* shared-state interactions are unclear
* expected behavior itself conflicts across sources

The correct result may be:

`UNKNOWN — requires escalation`

That is preferable to a confident false defect.

## Quality bar

Failure triage is successful when the next person can tell:

* whether meaningful execution occurred
* what failed first
* what evidence supports the classification
* whether the product actually violated a requirement
* whether the test itself is trustworthy
* whether configuration mattered
* how confident the diagnosis is
* what smallest next action will reduce uncertainty

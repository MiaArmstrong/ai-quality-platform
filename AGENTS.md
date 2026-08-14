# AGENTS.md — AI Quality Platform

This repository demonstrates a production-minded AI quality engineering system that combines requirements quality, agentic QA workflows, conventional test automation, AI/LLM evaluation, retrieval and organizational knowledge, release orchestration, observability, and human approval gates.

This file is the repository-wide operating contract for human contributors and AI coding agents.

## 1. Mission

Build an AI Quality Platform that helps an engineering team reason about software quality across the delivery lifecycle:

1. author and assess work items
2. gather relevant engineering context
3. plan testing
4. execute deterministic automation
5. evaluate nondeterministic AI behavior
6. diagnose failures
7. preserve reusable knowledge
8. assess release readiness

The goal is not to automate human judgment away. The system should automate objective, repeatable work and reserve human attention for decisions where independent judgment is valuable.

## 2. Source-of-truth hierarchy

When sources disagree, use this precedence unless a scoped `AGENTS.md` explicitly documents a stronger local rule:

1. Current executable behavior / source code
2. Canonical shared documentation
3. Approved work-item acceptance criteria / implementation spec
4. Validated operational memory
5. Unvalidated working notes
6. Agent inference

Never silently resolve a conflict. Surface it.

## 3. Knowledge architecture

### Shared knowledge

The GitHub Wiki is the canonical shared knowledge base for this project.

Use it for durable, team-wide, human-readable information such as:

- architecture
- product behavior
- API contracts
- testing strategy
- engineering standards
- known constraints
- release procedures
- validated operational rules

When a working-memory entry points to a GitHub Wiki page, the Wiki page is authoritative.

### Working memory

`knowledge/mempalace/`

Use for debugging history, test heuristics, temporary findings, environment quirks, investigation breadcrumbs, historical context, and pointers to shared documentation.

Working memory is not automatically authoritative.

### Promotion rule

When working memory becomes validated, broadly reusable, team-useful, and stable enough to maintain, promote it to the GitHub Wiki.

Then replace duplicated working-memory content with a short pointer/link to the canonical GitHub Wiki page.

### Memory hygiene

Before adding durable knowledge:

1. search for an existing entry
2. update rather than duplicate
3. store distilled facts, not raw dumps
4. preserve provenance
5. never store secrets, credentials, tokens, private customer data, or unredacted production logs

## 4. Agent context protocol

### Front-door agents

Agents starting a new work item are responsible for broad context gathering. Depending on the task, inspect the work item, acceptance criteria, linked work, shared knowledge, relevant working memory, current source code, existing tests, and recent implementation history where available.

Produce a concise **Files of Record / Sources of Record** map for downstream agents.

### Downstream agents

Do not repeatedly rediscover the entire system. Use the handoff artifact and open the specific files it identifies.

Still re-read the current work item, its acceptance criteria, and any scoped `AGENTS.md` affecting files you will modify.

## 5. Human gates and correlated-agent risk

Agents using the same or related models can share blind spots. Independent review by another agent is useful but is not equivalent to an independent human judgment.

For high-impact workflows, preserve explicit human gates at the most valuable control points.

### Design gate

For novel, cross-cutting, security-sensitive, high-risk, or expensive changes:

- architect proposes design
- adversarial verifier attempts to refute it
- human reviews both
- implementation begins only after approval

### Release / outward-action gate

Do not perform irreversible or externally visible actions without authorization when the workflow marks them as gated.

A stated goal is not equivalent to approval for a gated action.

## 6. Adversarial verification

Verification agents should try to prove the result wrong.

Ask:

- Can this pass without exercising the intended behavior?
- Is the assertion observing the authoritative state?
- Could the result be vacuously green?
- Does the test cover the actual acceptance criterion?
- Is the fixture deterministic?
- Does the test still fail if the regression is reintroduced?
- Is the result a product failure, test failure, orchestration failure, or unknown?
- Was relevant configuration accounted for?
- Did a workaround silently narrow the requirement?

Default to uncertain/refuted when evidence is insufficient.

## 7. Evidence and read-back

Successful execution is not proof of correctness.

For state-changing flows, prefer:

1. perform the action
2. observe the network/service result
3. validate important response data
4. read back persisted state from an authoritative interface
5. validate the user-visible result where applicable

For AI behavior, preserve prompt/input, retrieved context, model/provider/version where available, evaluation criteria, output, citations/provenance, latency, and token/cost metadata where available.

## 8. Deterministic test design

Tests should be independently runnable where practical, deterministic, explicit about starting state and configuration, observable, repeatable, and resistant to ambient-environment data.

### Never allow vacuous passes

If a test loops over returned data, assert the expected data exists first.

If a test depends on a fixture, create or seed it deterministically rather than scanning the environment and silently skipping when absent.

### Mutation verification for guards

When adding a regression guard for existing-correct behavior:

1. make the test pass against correct behavior
2. temporarily reintroduce the targeted regression
3. confirm the test fails for the expected reason
4. revert the mutation
5. record the verification result

## 9. Configuration-path coverage

Identify configuration, feature flags, model settings, permissions, or runtime modes that change the behavior being tested.

Distinguish behavior-changing settings from setup-only settings.

If a test changes shared configuration, capture the original value and restore it in teardown/finalization logic that runs even when the test fails.

## 10. Requirements quality

Work items should be objectively testable.

Use shared standards under `.agents/standards/`, including:

- `invest.md`
- `given-when-then.md`
- `definition-of-ready.md`
- `definition-of-done.md`
- `severity-vs-priority.md`

Never invent missing requirements.

## 11. Test automation conventions

Prefer intent-driven tests.

Use abstraction boundaries appropriate to the technology: page/screen objects, reusable components/fragments, workflow helpers, API clients, fixtures/builders, and evaluation helpers.

Before adding a new helper, search for an existing implementation and reuse, compose, parameterize, or thin-wrap where appropriate.

## 12. AI evaluation

AI/LLM features require evaluation beyond HTTP success.

Depending on the feature, evaluate relevance, groundedness, citation correctness, retrieval quality, instruction following, robustness, prompt injection resistance, harmful/unsafe behavior, tone/style requirements, latency, cost, and regression against curated datasets.

Evaluation criteria must be explicit.

## 13. Failure classification

Before reporting a defect, classify the failure:

- **PRODUCT**
- **TEST**
- **ORCHESTRATION**
- **ENVIRONMENT**
- **UNKNOWN**

Do not convert UNKNOWN into PRODUCT merely to produce a conclusion.

## 14. Release orchestration

Release-level testing should confirm the intended build/environment, inspect what changed, map changes to test areas, prioritize high-impact areas first, execute independent areas concurrently when safe, serialize shared-state tests when needed, parse raw execution evidence independently, reconcile passing tests with actual release coverage, identify uncovered/manual-only areas, and produce a concise release-level conclusion.

A green suite does not prove every release item was covered.

## 15. Documentation synchronization

When behavior changes, update the documentation that claims to describe that behavior.

If a human-facing coverage document exists, scenario additions, removals, renames, skips, or material validation changes must update that documentation in the same change.

## 16. Security and privacy

Never commit API keys, access tokens, passwords, private certificates, customer PII, proprietary production payloads, secrets copied from logs, or confidential employer material.

Use synthetic data in examples.

## 17. Scope boundaries

Read the nearest `AGENTS.md` before modifying files.

A nested `AGENTS.md` may add stricter rules for its subtree, but may not silently weaken repository-level safety, evidence, or knowledge-governance rules.

## 18. Before making changes

1. Read this file.
2. Read the current work item.
3. Read relevant scoped `AGENTS.md` files.
4. Inspect shared knowledge.
5. Inspect relevant working memory.
6. Search for existing implementation/tests.
7. Identify authoritative evidence.
8. Identify relevant configuration paths.
9. Determine whether a human gate is required.

## 19. After meaningful work

1. Run scope-appropriate tests.
2. Record evidence.
3. Update affected documentation.
4. Update working memory with concise reusable findings.
5. Promote durable team knowledge when appropriate.
6. Link working-memory entries to canonical shared docs.
7. Report unresolved conflicts, assumptions, and unknowns.
8. Do not claim completion if required validation was not run.

## 20. Definition of done for agent work

Agent work is complete when requested behavior is implemented or analysis is complete, acceptance criteria are addressed, relevant tests/evaluations exist, validation was run where possible, evidence supports the conclusion, documentation is synchronized, durable knowledge is captured appropriately, secrets/private information were not introduced, and unresolved uncertainty is clearly reported.

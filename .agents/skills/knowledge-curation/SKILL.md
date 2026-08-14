---

name: knowledge-curation
description: >
  Curate operational and canonical project knowledge produced during engineering,
  QA, AI-evaluation, and agent workflows. Deduplicate findings, preserve provenance,
  distinguish working memory from canonical shared knowledge, identify stale or
  conflicting information, promote validated team-wide knowledge to the GitHub Wiki,
  and maintain pointers through memPalace-style memory and knowledge/wiki-map.md.
---

# Knowledge Curation

## Purpose

Keep project knowledge useful over time instead of allowing agent workflows to create a growing pile of duplicated notes.

This skill manages the transition from:

```text
observation
   ↓
working knowledge
   ↓
validated operational knowledge
   ↓
canonical shared knowledge
```

The goal is not to save everything.

The goal is to preserve the smallest amount of high-value knowledge needed for future humans and agents to work effectively.

## Knowledge architecture

### GitHub Wiki

The GitHub Wiki is the canonical shared knowledge base.

Use it for durable, broadly reusable team knowledge such as:

* architecture
* product behavior
* integration contracts
* test strategy
* operational procedures
* known system constraints
* AI evaluation strategy
* release procedures
* stable failure patterns
* shared engineering/QA guidance

### memPalace-style working memory

Use `knowledge/mempalace/` for operational knowledge that is:

* still being investigated
* useful to agents during active work
* narrower than team-wide documentation
* historical context
* an implementation/testing heuristic
* a pointer to canonical documentation

Working memory is not automatically authoritative.

### Wiki map

Use:

`knowledge/wiki-map.md`

as the lightweight agent-facing index to major canonical Wiki pages.

Do not attempt to mirror the entire Wiki in the repository.

## Core rules

* Search before adding.
* Update existing knowledge instead of duplicating it.
* Store distilled facts, not transcript-sized notes.
* Preserve provenance.
* Separate observation from inference.
* Do not promote unverified information.
* Do not store raw logs unless they are the artifact being referenced.
* Do not turn a one-off ticket detail into permanent organizational knowledge.
* GitHub Wiki wins over duplicate memPalace detail when the Wiki is current and verified.
* Current executable behavior can reveal that documentation is stale; flag the conflict rather than silently rewriting history.
* Never store secrets, credentials, tokens, private user data, or confidential production data.

## Model routing

Default tier: **economy**

Knowledge curation is usually structured summarization, deduplication, and indexing.

Escalate to **standard** when:

* sources conflict
* deciding whether something is stable enough for promotion
* documentation and code disagree
* multiple similar entries must be semantically reconciled
* provenance is unclear

Escalate to **high reasoning** only when resolving the knowledge conflict requires meaningful architectural or cross-system judgment.

Do not use a stronger model merely for rewriting prose.

## Inputs

Potential inputs include:

* QA intake findings
* failure triage
* automation implementation results
* release-testing findings
* architecture decisions
* test execution evidence
* AI evaluation results
* agent handoffs
* existing memPalace entries
* GitHub Wiki pages
* `knowledge/wiki-map.md`

## Flow

### 1. Extract candidate knowledge

Identify findings that may remain useful after the current task.

Good candidates include:

* stable product behavior
* important configuration behavior
* reusable debugging knowledge
* recurring failure mechanisms
* architecture boundaries
* reliable test setup requirements
* authoritative evidence/read-back methods
* integration quirks
* AI-system evaluation expectations
* release constraints
* durable QA heuristics

Usually do not retain:

* temporary status updates
* raw command transcripts
* entire logs
* obvious facts directly visible in code
* ticket-specific narrative
* speculative root causes
* resolved one-time environment incidents
* repeated information already documented canonically

### 2. Classify each candidate

Assign one class:

#### WORKING

Useful but unvalidated or investigation-stage.

Store in memPalace.

#### VALIDATED OPERATIONAL

Evidence-supported and reusable, but still narrow or operational.

Store in memPalace.

#### CANONICAL SHARED

Stable, broadly useful, team-facing knowledge.

Promote to GitHub Wiki when authorized.

#### TRANSIENT

Not worth retaining.

Discard after the workflow.

Example:

```text
Finding:
Quote submission reads configuration before building the request.

Class:
CANONICAL SHARED

Reason:
Stable product behavior affects implementation and testing across multiple tickets.
```

### 3. Search existing knowledge

Before creating anything new, search:

* relevant memPalace entries
* `knowledge/wiki-map.md`
* corresponding GitHub Wiki pages where available

Determine whether the finding is:

* NEW
* DUPLICATE
* EXTENSION
* CORRECTION
* CONFLICT
* TRANSIENT

### 4. Deduplicate

#### DUPLICATE

Do not create another entry.

Optionally strengthen the existing entry with new provenance.

#### EXTENSION

Update the existing entry with only the new useful fact.

#### CORRECTION

Update the existing entry and preserve enough provenance to explain why.

Do not keep obsolete detail merely because an agent wrote it previously.

#### CONFLICT

Do not choose a winner silently.

Record:

* source A
* source B
* nature of conflict
* freshness
* evidence strength
* recommended verification

Escalate if necessary.

### 5. Validate provenance

Each retained operational fact should answer:

> How do we know this?

Useful provenance may include:

* source file
* test scenario
* API response
* implementation path
* issue/PR identifier
* Wiki page
* release result
* evaluation dataset
* date/version when temporally relevant

Example:

```yaml
fact: Quote status is persisted before the customer notification is emitted.
source:
  type: integration-test
  reference: tests/integration/quote-status.spec.ts
validated: true
```

Do not treat an earlier agent statement as evidence by itself.

### 6. Write/update memPalace

Keep entries concise.

Recommended structure:

```markdown
# <Topic>

## Summary

<distilled operational knowledge>

## Status

WORKING | VALIDATED OPERATIONAL

## Evidence

- <source>
- <source>

## Canonical documentation

- GitHub Wiki: <page>

## Notes

<only useful caveats/history>
```

Avoid chronological diary-style memory.

Prefer current useful state.

### 7. Decide whether to promote

Promote to the GitHub Wiki when the knowledge is:

* validated
* stable
* useful across multiple future tasks
* relevant to more than one person/agent
* important enough that relying on local working memory would be risky

Do not promote merely because information is interesting.

### 8. Promotion workflow

When promotion is appropriate and authorized:

1. verify the finding
2. search the target Wiki page
3. update an existing canonical page when practical
4. create a new page only when the topic deserves its own durable home
5. avoid copying ticket-specific noise
6. update `knowledge/wiki-map.md` if a new major page was created
7. replace redundant memPalace detail with a pointer where appropriate
8. preserve narrow operational details in memPalace only when they remain useful

### 9. Canonical pointer behavior

After promotion, memPalace should generally become smaller.

Example:

```markdown
# Quote Configuration

Canonical behavior is documented in:

GitHub Wiki: Quote-Lifecycle

Operational note:

When debugging quote tests, verify the account configuration through the settings API before assuming the request payload is wrong.
```

Do not maintain two full copies of the same canonical documentation.

### 10. Detect stale knowledge

Flag possible staleness when:

* code contradicts documentation
* recent tests contradict an older entry
* a referenced component no longer exists
* a setting/feature flag changed meaning
* an API contract changed
* a Wiki page points to removed files
* a memory entry references obsolete behavior

Mark:

`POTENTIALLY STALE`

until verified.

Do not automatically assume code is correct and documentation is wrong; a code regression is also possible.

### 11. Handle conflicting authority

When two sources disagree, evaluate:

* which is canonical
* which is newer
* whether the newer source is validated
* whether executable behavior may itself be defective
* whether the disagreement concerns intended behavior or current behavior

Example:

```text
Wiki:
Refunds must preserve the original payment method.

Current code:
Refund endpoint accepts an alternate method.

Ticket:
Claims alternate method is intended.

Result:
CONFLICT — requires product/engineering confirmation.
```

Do not erase the conflict by choosing whichever source is easiest.

### 12. AI-system knowledge

For AI/LLM systems, useful durable knowledge may include:

* model-routing policy
* evaluation thresholds
* approved datasets
* retrieval architecture
* known model limitations
* prompt/instruction contracts
* required citation behavior
* escalation policies
* latency/cost targets
* evaluator reliability findings

Avoid storing individual model outputs unless they are part of a curated regression/evaluation dataset.

## Output

Produce a concise curation report:

```markdown
# Knowledge Curation

## Candidates Reviewed

### <finding>

Classification:
WORKING | VALIDATED OPERATIONAL | CANONICAL SHARED | TRANSIENT

Action:
CREATE | UPDATE | PROMOTE | LINK | DISCARD | FLAG CONFLICT

Reason:
...

Provenance:
...

## Deduplication

<entries reused/merged>

## Canonical Updates

<Wiki pages updated/recommended>

## Wiki Map Updates

<changes or "None">

## Stale / Conflicting Knowledge

<issues or "None">

## Memory Updates

<memPalace changes>

## Unresolved Questions

<remaining uncertainty>
```

## Outward actions

Knowledge analysis is read-only by default.

Do not automatically:

* edit the GitHub Wiki
* create Wiki pages
* modify shared documentation
* delete existing knowledge
* publish external information

unless the active orchestration workflow authorizes the action.

Local working-memory updates may be allowed by the repository's active instructions.

## Privacy and secret hygiene

Never persist:

* passwords
* API keys
* access tokens
* private keys
* session cookies
* production credentials
* customer PII
* confidential raw conversation data
* secrets found accidentally in logs

If a useful finding depends on secret-bearing evidence, retain only the non-secret distilled fact and a safe reference where appropriate.

## No knowledge inflation

More memory is not automatically better memory.

Prefer:

```text
20 high-value validated entries
```

over:

```text
2,000 loosely related agent notes
```

Measure knowledge quality by whether it reduces future rediscovery and improves decisions.

## Feedback signal

Useful curation metrics may include:

* duplicate-entry rate
* percentage of memory entries with provenance
* stale-entry detection rate
* canonical promotion rate
* frequency agents rediscover already-known information
* frequency agents retrieve the correct canonical page
* number of unresolved knowledge conflicts
* token reduction from pointer-based handoffs

These metrics can later feed the AI-quality platform's observability layer.

## Quality bar

Knowledge curation succeeds when:

* useful findings survive
* noise does not
* facts have provenance
* working memory stays compact
* canonical documentation stays discoverable
* agents do not repeatedly rediscover the same information
* conflicts are visible
* stale knowledge is detectable
* GitHub Wiki remains the shared source of truth

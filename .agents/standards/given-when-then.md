# Given / When / Then Acceptance Criteria

Use for Stories, New Features, Improvements, and Tasks with user-observable behavior.

## Structure

```text
GIVEN <precondition / starting state>
WHEN  <single action or event>
THEN  <observable outcome>
AND   <additional observable outcome>
```

## Rules

- One scenario per acceptance-criteria block.
- `GIVEN` describes state, not an action sequence.
- `WHEN` contains the triggering action/event.
- `THEN` must be objectively observable.
- Avoid implementation language.
- Include negative and failure cases when meaningful.
- Prefer measurable outcomes over words such as "correctly", "properly", or "gracefully".

For tiny UI/copy changes, a rule-oriented checklist is acceptable if every item remains specific and observable.

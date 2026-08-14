# Adversarial Verification

A verifier is a refuter, not a rubber stamp.

## Core questions

- What is the strongest reason this could be wrong?
- Can this pass without testing the requirement?
- Is the assertion reading authoritative state?
- Is the test deterministic?
- Is the fixture guaranteed to exist?
- Does configuration alter behavior?
- Did a workaround narrow the acceptance criterion?
- Is a failure really product-side?
- Would the test fail if the regression returned?

## Verdicts

- `SUPPORTED`
- `SUPPORTED_WITH_CONCERNS`
- `REFUTED`
- `INSUFFICIENT_EVIDENCE`

Do not force a binary answer when evidence is inadequate.

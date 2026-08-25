# Roadmap

Roadmap work is tracked in GitHub Issues. An issue describes intended work; it
does not imply that the capability is implemented.

## Runtime and security hardening

- [#2 Run leasing and concurrent resume protection](https://github.com/MiaArmstrong/ai-quality-platform/issues/2)
- [#3 Filesystem path canonicalization](https://github.com/MiaArmstrong/ai-quality-platform/issues/3)

## Optional architecture improvements

- [#4 Declarative semantic rule registry](https://github.com/MiaArmstrong/ai-quality-platform/issues/4)
- [#5 Configurable warning policy](https://github.com/MiaArmstrong/ai-quality-platform/issues/5)
- [#6 Reusable authorization policy profiles](https://github.com/MiaArmstrong/ai-quality-platform/issues/6)

## Execution and action integration

- [#7 Isolated real action adapters](https://github.com/MiaArmstrong/ai-quality-platform/issues/7)

This work must define a threat model and isolation boundary before enabling real
filesystem, shell, GitHub, Wiki, deployment, or ticketing side effects.

## Provider expansion

- [#8 Additional provider-enabled roles](https://github.com/MiaArmstrong/ai-quality-platform/issues/8)

Candidate roles require canonical artifact contracts, semantic invariants,
routing and escalation behavior, telemetry, and preserved authorization
boundaries. Architect, Requirements Analyst, and Adversarial Verifier have now
completed bounded real-provider demonstrations, including a multi-role path to
the pending human `qa_signoff` gate. Issue #8 remains open because its
economy-tier real-provider role criterion is still outstanding.

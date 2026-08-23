# Provider adapter working note

- Provenance: `feat/provider-adapter`, 2026-08-17.
- The offline mock remains the default executor.
- Real model execution is role-scoped, JSON-Schema constrained, and records prompt-source hashes.
- Provider access carries no tool authority; authorization remains a separate application control.
- Model IDs are supplied through tier-specific environment variables.
- Cost estimates require explicit pricing configuration.
- OpenAI strict Structured Outputs require a provider-subset transport schema:
  explicit types, every object property required, `additionalProperties: false`,
  and no unsupported composition. Canonical-only constraints are revalidated
  after response rather than discarded.
- A 2026-08-23 Architect smoke retry reached the Responses API but returned an
  empty-detail HTTP 400 before model execution. Preserve the SDK error body in
  either direct or nested form and the safe `x-request-id`; do not infer schema
  rejection from status alone.
- The successful 2026-08-23 smoke exposed a schema-valid semantic conflict:
  `outcome=success` with Architect `escalation_requested=true`. Provider outputs
  now require provider-neutral semantic validation before artifact acceptance;
  repairable invalid output gets one repair and retains both raw evidence and
  structured findings.
- See `orchestration/README.md` for the maintained operational contract.

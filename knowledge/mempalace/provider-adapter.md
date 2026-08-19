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
- See `orchestration/README.md` for the maintained operational contract.

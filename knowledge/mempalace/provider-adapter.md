# Provider adapter working note

- Provenance: `feat/provider-adapter`, 2026-08-17.
- The offline mock remains the default executor.
- Real model execution is role-scoped, JSON-Schema constrained, and records prompt-source hashes.
- Provider access carries no tool authority; authorization remains a separate application control.
- Model IDs are supplied through tier-specific environment variables.
- Cost estimates require explicit pricing configuration.
- See `orchestration/README.md` for the maintained operational contract.

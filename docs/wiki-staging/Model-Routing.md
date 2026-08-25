# Model Routing

## Logical tiers

- `economy`: mechanical extraction, summarization, and lower-complexity work;
- `standard`: ordinary analysis and implementation reasoning;
- `high_reasoning`: architecture, adversarial verification, and ambiguous or
  cross-system decisions.

These are provider-neutral contracts. Concrete model IDs are configuration, not
architectural truth, and must not be embedded in role or workflow definitions.

## Selection principle

The routing policy chooses the least-expensive tier expected to perform a role
reliably. Registered transitions define when escalation or de-escalation is
valid. Escalation must move to a genuinely higher tier and is finite; a request
at the highest available tier becomes structured insufficient evidence rather
than an endless retry.

## Telemetry

Routing records include workflow, task, role, requested and selected tiers,
reason, transition type, and attempt. Provider telemetry separately records the
resolved model, latency, token usage, cached-read and cache-write tokens, and estimated cost when
pricing is configured.

## Current provider configuration

The OpenAI adapter resolves tier mappings from environment variables. Mapping a
tier to a particular OpenAI model is an operational configuration choice and may
change without changing the role or workflow contract.

Optional pricing is also configuration-driven. `AQP_OPENAI_PRICING_JSON` maps a
resolved model to per-million rates for normal input, cached input, cache writes,
and output. The runtime returns a null observed estimate if any required rate or
usage detail is absent. Demo preflight separately reports a conservative ceiling;
that ceiling is not expected spend.

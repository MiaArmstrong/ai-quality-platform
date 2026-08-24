# Authorization and Human Gates

## Capability governance

`.agents/capabilities.v1.json` defines stable capability IDs. Each role has an
explicit policy with allowed, denied, gated, and scoped capabilities. Unknown or
undeclared capability use is denied by default.

Executable workflow tasks declare artifact reads and writes. The runtime checks
the role policy and exact artifact resource before loading or persisting each
artifact. Task-scoped repository permissions do not expand beyond authorized
paths.

## Gated capabilities

Gated capability approval is resolved from SQLite runtime state rather than from
a caller-supplied trusted flag. Resolution checks the gate ID, workflow run, gate
type, approved status, policy version, capability, resource hash, approver,
decision time, and current evidence hashes.

Authorization decisions are persisted before a denial or unmet gate aborts
execution.

## Workflow human gates

Design and release gates store the active evidence artifact IDs and hashes.
Changing referenced evidence marks pending or approved gates stale. Immediately
before approval, the runtime compares the gate evidence with active artifacts.
Rejection transitions to explicit rework rather than being treated as an
execution exception.

## Security boundary

This is application-level governance, not OS isolation. It can prevent the
current runtime from authorizing an operation, but future real adapters must also
canonicalize resources and use suitable process, filesystem, credential, or
container isolation. Issues #3 and #7 track that work.

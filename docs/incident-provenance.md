# Historical incident receipt consumer

`incident_provenance.read_historical_incident_commit` takes the governed
primary repository checkout and an `IncidentCommitQuery`. It resolves that
repository's registered orchestrator installation and invokes its public
`scripts/bin/incident_authority.py read-history` command through the canonical
credential wrapper, with a thirty-second process bound.

The query binds repository, item, attempt, phase, operation, generation, owner,
original base/head, PR number and the landed commit/tree being inspected. A
schema-1 response must match that identity and the exact corresponding pair in
the full landed commit/tree sequence. The result preserves original paths,
deferred work, repayment status and both historical/current token identities.
Labels and incident environment variables do not supply historical evidence.

The producer authenticates the canonical ledger token chain. This consumer
checks its process protocol and attribution; it has no second authority store,
token-chain parser or authority-bootstrap operation. An unavailable installation,
process failure, malformed reply or identity mismatch returns a named failure.
Canonical refusal codes remain visible instead of becoming ordinary admission.

A historical reply must explicitly deny current effects and normal factory
proof. The returned attribution does not select an execution mode, create TDD or
coverage evidence, authorize a workflow edit or close the incident. Scoped host
workflow authorization remains a separate required input.

This delivers a process consumer, not live policy reductions. Commit/range/replay
and host-authority entrances still require integration with the released,
installed canonical producer and their own mode-specific evidence rules. Until
that producer is available, the consumer refuses; fixture protocol proofs do
not claim live incident authorization or fleet adoption.

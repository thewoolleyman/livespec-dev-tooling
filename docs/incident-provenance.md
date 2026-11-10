# Historical incident receipt consumer

`incident_observer_provenance.ObserverProvenance` is the one implementation of the
historical provenance lookup. It takes an `IncidentCommitQuery` and invokes the
installed orchestrator's public `scripts/bin/incident_authority.py read-history`
command through the canonical credential wrapper, with the one authority-call
ceiling `incident_authority_client.AUTHORITY_CALL_CEILING_SECONDS`. The shared
`_incident_provenance_protocol.decode_historical_result` decodes the reply. The
observer's `POST /provenance` route is the only entrance the range gate uses.

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

An attempt's recorded head is provenance too, so an unmerged expedited PR's commit
is admitted before any landed pair exists.

## The range gate

Hosted CI holds no tenant credential, so `check-red-green-replay` cannot run this
reader itself. The observer runs it on its host behind the query-only
`POST /provenance` route (`incident_observer_provenance`), and
`checks/_red_green_replay_incident` asks that route last, for a commit that still
lacks TDD evidence. The PR's `livespec-incident-ci` block only locates the attempt,
and the commit's `Factory-Override: EXPEDITED_INCIDENT_RESPONSE flag: <item>` trailer
must name that item, but neither grants anything: a commit passes only when the
chain records the PR's exact base and head and the commit is in that head's history.
Labels and incident flags are never read. Every other answer keeps the commit
convicted, and a PR with no block makes no request.

Host-authority entrances still need their own integration.

# Incident CI execution plans

`incident_ci_policy.select_ci_plan` computes a head-bound plan from an authenticated
forge event, a released check inventory, and independent trust readers. It does
not install workflow changes, grant workflow-write permission, execute checks, or
publish a forge status. The existing normal CI graph remains unchanged.

An incident PR requires its projected label, the canonical current attempt bound
to its exact repository, PR, base/head, repair operation, owner and generation,
and an independently admitted premerge observer arm. A historical receipt alone
cannot authorize selection. `CiTrust.current` authenticates the attempt;
`CiTrust.observer` must query the independently provisioned controller, validate
its released build and generation fence, and bind the arm to the exact PR/head
and canonical receipt digest. An ambient flag or candidate JSON is not a reader.
The future master run and landed SHA are bound by the controller after merge;
they cannot be required before those identities exist.

The trusted inventory describes each target's batch, classification, target
dependencies and artifact producers/consumers. Incident selection retains declared
fast members in their original order and batch. Coverage and spec work, unknown
work, and indirect consumers of omitted producers are explicit deferrals.
Known coverage/spec target names retain those roles even if marked fast. An empty
retained gate is refused. The inventory must come from the released policy,
rather than an untrusted subset supplied by the candidate tree.

`aggregate_ci_results` consumes authenticated executed member results and the
independently supplied complete inventory. It recomputes the expected plan,
rechecks current head/mode and the controller arm fence, and rejects stale,
duplicate or foreign evidence and constructed plans. Its stable context name is
`ci-green`; actual passes, failures, missing work and intentional deferrals remain
separate. A selected check reported skipped, cancelled, unavailable or deferred
cannot satisfy the aggregate. A frozen already-authorized controller grant can
remain the fence during a tenant outage; this does not invent new authority.

Every push and every ordinary CI event retains the entire supplied normal graph.
The canonical normal-child transformation removes both incident flags and the
context carrier before inherited malformed values can affect execution. Master
selection never consults incident labels or current-attempt readers.

This is the independently testable policy slice of `livespec-dev-tooling-egy3ri`.
Workflow, reusable-workflow, direct Action, aggregate publisher and parity/template
wiring still require the scoped maintainer authorization and publication guards,
released current-reader/controller services, and actual installed integration
proof. This branch edits no workflow and grants no bypass. The child remains
incomplete until those existing obligations are delivered under the same carrier.

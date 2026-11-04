# Bounded incident gate execution

`incident_local_gates` and `incident_gate_inventory` provide the local selection
and execution foundation for `livespec-dev-tooling-cerkbn`. They do not yet enable
incident commits or pushes. The work item remains open until the actual hook,
aggregate, delegation and replay entrances use a trusted incident boundary.

The inventory reader preserves the population and order of `check-targets.txt`.
Only one exact `incident-timing: fast` annotation selects a target; slow, missing,
invalid, conflicting and duplicate declarations produce explicit deferrals.
Purity declarations continue to describe normal memoization independently.
The two annotated existing recipes, `check-lint` and `check-format`, were measured
at 1.93 and 1.57 seconds on 2026-11-03. Those measurements are not a portable
promise: every selected invocation still has its own sixty-second ceiling.

The executor launches selected commands sequentially in separate owned process
groups. It captures real failure output and exit status. A command that reaches
the ceiling receives process-group termination and a `deferred-timeout` result,
without a passing return code. The report is `expedited-local-partial`; it must
never be written as a normal full-suite, coverage-cache or factory verdict.

`route_resolved_gates` accepts the canonical resolver's context structurally.
Normal mode returns `None`, allowing the caller's existing normal body to
continue. Repair executes the selected local gates; a recorded emergency revert
defers all gates. An unsupported mode or missing incident identity refuses with
status 78. This function is an execution seam, not an identity authenticator:
constructing an object with matching attributes does not authorize an incident.

## Required entrance integration

The shared boundary must authenticate the current repository, attempt, phase,
base/head, operation owner and generation before calling the canonical resolver.
For reverts, it must also establish the recorded merge and authorized inverse.
The versioned transport compares an independently trusted context; an ambient
`LIVESPEC_INCIDENT_CONTEXT` value cannot supply that trust.

These independently invocable surfaces must route through that boundary before
their first relevant effect:

| Surface | Resolve before |
| --- | --- |
| `check-pre-commit` | Staged-file prechecks, delegation and doc-only/Red selection. |
| `lint-autofix-staged` | Ruff mutation, formatting or adding changed files. |
| `check-commit-pairs-source-and-test` | Source/test pairing selection. |
| `check-pre-push` | Normal token lookup, cluster credential checks or submission. |
| `check`, `check-scoped`, `check-changed` | Runtime synchronization, member selection, aggregate or evidence execution. |
| Direct coverage entrances | Normal cached coverage lookup or coverage execution. |
| `pre_commit_delegate` and `gate_remote_delegate` | Configuration routing, credential probing, remote assembly or submission. |
| `check-red-green-replay` | Normal evidence lookup, replay venue selection or suite execution. |
| Detached gate runner | Any independent command selection before a child launch. |

The boundary needs explicit normal-continuation versus terminal incident/refusal
results, a runtime available before synchronization, and a durable partial-receipt
sink bound to the incident identity. It must avoid selecting the normal aggregate
through a nested wrapper or running one aggregate per hook member.

Trusted normal master and normal repayment must use the canonical normal child
environment transformation before invoking normal callbacks. The installed
credential wrapper preserves caller environment: omitting keys from an overlay
does not unset inherited incident flags or the carrier. Use complete replacement
or explicit unsets at the child boundary, rather than assuming the wrapper scrubs.

At publication, the authoritative lifecycle receipt/ownership loader, durable
receipt sink and released process entry API are still integration prerequisites.
This foundation installs no shell flag conditionals, alternate receipt parser,
normal fallback after an incident refusal, hook bypass or production caller.
Its focused evidence exercises selection, actual failures, timeout descendant
termination, inventory parsing and the structural context adapter. Actual hook
and released fleet incident drills remain owed under the same work item and plan.

# Bounded incident gate execution

`incident_local_gates` and `incident_gate_inventory` provide the local selection
and execution foundation for `livespec-dev-tooling-cerkbn`. They do not yet enable
incident commits or pushes by themselves. The hook entrance and the direct gate
entrances below now resolve incident mode through a trusted shared boundary.

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
their first relevant effect. The last column records what is wired today.

| Surface | Resolve before | Wired through |
| --- | --- | --- |
| Installed `pre-commit`, `commit-msg`, `pre-push` hooks | Lefthook autofix, pairing, normal evidence or delegation. | `incident_hook_entry` (the hook entrance). |
| `check-pre-commit` | Staged-file prechecks, delegation and doc-only/Red selection. | `incident_gate_entry`, first act of `scripts/just/check-pre-commit.sh`. |
| `lint-autofix-staged` | Ruff mutation, formatting or adding changed files. | `incident_gate_entry`, first act of `scripts/just/lint-autofix-staged.sh`. |
| `check-commit-pairs-source-and-test` | Source/test pairing selection. | `IncidentEntrance` on `checks/commit_pairs_source_and_test.main`. |
| `check-pre-push` | Normal token lookup, cluster credential checks or submission. | `incident_gate_entry`, first act of `scripts/just/check-pre-push.sh`. |
| `check`, `check-scoped`, `check-changed` | Runtime synchronization, member selection, aggregate or evidence execution. | `incident_gate_entry`, first act of each `scripts/just/` body. |
| Direct coverage entrances (`check-coverage`, `check-per-file-coverage`) | Normal cached coverage lookup or coverage execution. | `incident_gate_entry`, first act of each `scripts/just/` body. |
| `pre_commit_delegate` and `gate_remote_delegate` | Configuration routing, credential probing, remote assembly or submission. | `IncidentEntrance` on each `main`. |
| `check-red-green-replay` | Normal evidence lookup, replay venue selection or suite execution. | `IncidentEntrance` on `checks/red_green_replay.main`. |
| Detached gate runner | Any independent command selection before a child launch. | `gate_runner_delegate.main` (the venue selection `gate-run.sh` calls before launch). |

### The direct-entrance boundary

`livespec_dev_tooling/incident_gate_entry.py` (livespec-dev-tooling-6bmta2, with
the last four entrances wired by livespec-dev-tooling-wjmre6) is the shared
boundary for every direct entrance. It reuses the hook entrance's
shared truth-value parser and its registered-authority trust path
(`parse_query`, `invoke_authority` `read-current`, `resolve_current`), so there is
one parser and one notion of a trusted incident context. Its outcomes:

| Condition | Outcome | Exit (CLI) |
| --- | --- | --- |
| Both flags unset or explicitly false | `normal`: the entrance's complete normal body runs unchanged. | 75 |
| A malformed flag value | `invalid-incident-flag` configuration refusal. | 78 |
| A flag set without a trusted incident receipt | `untrusted-incident-receipt` refusal; no gate work. | 78 |
| A trusted incident at a direct entrance | `no-direct-incident-mode` refusal; no gate work. | 78 |
| A trusted incident at the detached runner | Continue on the LOCAL venue only. | n/a |

Every refusal prints `incident-gate-refused: <surface>: <code>: <detail>` on
stderr. Incident gates are selected only by the hook entrance, so a direct
aggregate never runs nested and never falls back to normal mode after an
incident request. The detached runner is the one launcher: its child is itself a
hook-mediated operation that resolves again, so it continues a trusted incident,
locally, and its cluster `run` submission refuses one.

The shell bodies keep the installed hook's presence prefilter: when no incident
variable is present at all they start no interpreter and run byte-for-byte as
before. When any is present, only the boundary's 75 continues; every other
status, including an unavailable boundary, is terminal.

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
The cerkbn foundation installs no shell flag conditionals, alternate receipt
parser, normal fallback after an incident refusal, hook bypass or production
caller. The direct-entrance presence prefilters above decide nothing about a
flag's value; the shared parser does.
Its focused evidence exercises selection, actual failures, timeout descendant
termination, inventory parsing and the structural context adapter. Actual hook
and released fleet incident drills remain owed under the same work item and plan.

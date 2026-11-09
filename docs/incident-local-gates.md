# Bounded incident gate execution

`incident_local_gates` and `incident_gate_inventory` provide the local selection
and execution foundation for `livespec-dev-tooling-cerkbn`. They do not yet enable
incident commits or pushes by themselves. The hook entrance and the direct gate
entrances below now resolve incident mode through a trusted shared boundary.

The inventory reader preserves the population and order of `check-targets.txt`.
It reads members through `check_inventory`, the same membership rule the normal
aggregate applies, so the incident path sees exactly the members `just check`
runs. Only one exact `incident-timing: fast` annotation selects a target; slow,
not-applicable, missing, invalid, conflicting and duplicate declarations
produce explicit deferrals. `fast` means fast AND applicable: a gate that
encodes a normal-path precondition an incident commit cannot meet by design is
`not-applicable`, and its `incident-precondition` annotation names that
precondition in the deferral reason. Purity declarations continue to describe
normal memoization independently. Every member carries a class from 2026-11-09
(livespec-dev-tooling-oqpw6t): 75 are `fast`, 7 are `slow` and 3 are
`not-applicable`. The timings were measured with each gate alone, so they are
not a portable promise: every selected invocation still has its own
sixty-second ceiling, and a deferral names the concurrency it ran under. The CI
entrance's packaged inventory takes its classes from the same annotations
through the same reader.

The executor is the normal aggregate's own runner (`_check_target_runner`), the
one `parallel_check_dispatcher` uses. Selected commands run in parallel under
the same worker cap, with stdin closed and output spooled to a temporary file.
Because a deadline must be able to kill a command's descendants, each command
here gets its own session, its process group is killed when it ends, and on
Linux it runs under a parent-death signal; `_check_target_isolation` states the
residual risk. A coverage-touching gate gets the same isolated `COVERAGE_FILE` and
`TMPDIR` the normal aggregate gives it, and a coverage consumer waits for its
producer and is deferred when the producer does not pass. The expedited path
adds only the per-command deadline: a command that
reaches the ceiling receives process-group termination and a `deferred-timeout`
result, without a passing return code. The report is `expedited-local-partial`;
it must never be written as a normal full-suite, coverage-cache or factory
verdict.

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
| A trusted normal origin: a master-push CI job or a factory sandbox | `normal`: the complete normal body runs with either flag inherited at any value, including a malformed one; the flags are never parsed. | 75 |
| Both flags unset or explicitly false | `normal`: the entrance's complete normal body runs unchanged. | 75 |
| A malformed flag value | `invalid-incident-flag` configuration refusal. | 78 |
| A flag set without a trusted incident receipt | `untrusted-incident-receipt` refusal; no gate work. | 78 |
| A trusted incident at a direct entrance | `no-direct-incident-mode` refusal; no gate work. | 78 |
| A trusted incident at the detached runner | Continue on the LOCAL venue only. | n/a |

A trusted normal origin is named by `livespec_dev_tooling/incident_trusted_origin.py`
(livespec-dev-tooling-wtsntu) before the flags are read: `GITHUB_ACTIONS=true` with
`GITHUB_EVENT_NAME=push` (this repository's CI triggers a push only on master) is
`NORMAL_MASTER`, and a checkout whose git config sets `livespec.sandboxExempt` to
`true` is `NORMAL_FACTORY_FOLLOW_UP`. The sandbox marker is probed only when an
incident variable is present. Both signals are ambient, which is sound because
they can only select the COMPLETE normal body: a forged signal makes an entrance
ignore a flag and apply full policy, and never grants an incident exception. An
origin outside these two (a pull-request job, a developer host) still parses the
flags and refuses a malformed one with `invalid-incident-flag` and an unverified
one with `untrusted-incident-receipt`. The installed hook entrance does not use
this trust path.

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

# Original incident run evidence

`ForgeRunReader` makes bounded read-only requests for the original GitHub run
attempt, its complete paginated job listing and workflow bytes at its original
merge revision. It never cancels, deletes or reruns jobs. A partial listing,
changed pagination total, foreign identity, unavailable credential or mismatched
source digest refuses. The original attempt endpoint excludes later job reruns.
The default transport uses the fleet's canonical budgeted GitHub client with
at most ten seconds per read and one collection deadline. An explicitly
provisioned local provider executable can supply the same read-only protocol.

`OriginalRun` must come from a retained canonical receipt and trusted resolver of
the original source graph, including expanded matrix job names and dependencies.
A graph inferred from a later checkout or from jobs that happened to exist is
insufficient. The provider checks the actual original workflow source digest;
canonical authorization authenticates the identity and the complete resolved
expected graph. An unsupported graph must refuse rather than omit jobs.

`build_run_evidence` retains every observed job alongside the expected graph.
Expected jobs have separate completed, failed, prerequisite-blocked, cancelled,
never-created, pending, skipped and unverified dispositions. A completed workflow
cannot prove a missing job executed. Every check without original-tree evidence
has a debt naming its owner, original tree and explicit proof continuation.
Failure evidence remains a failure rather than missing proof. Collection may
continue after revert or replacement without attributing a later run to the old
merge. An identified continuation can repay missing proof; a full rerun does not
hide a flake and a replacement observation does not erase earlier receipts.

`OriginalRunCollector` retains content-addressed evidence under
`original_run_evidence` in the independent observer's existing controller record.
It preserves all other fields and stores no lifecycle phase or new current
attempt. Provider and canonical calls run outside the repository action lock,
so slow collection cannot delay the first-failure inverse. A canonical outage
leaves the exact evidence and owned debt durable for reconciliation. The
canonical `record` adapter must be idempotent by evidence digest.

Correction is a proposal to the canonical writer. It preserves the original
item, PR, merge, revert, run, graph, failures and debt identities and binds the
classification to the complete evidence digest. A proposal requires an actual
repair diff or measured resolutions of every unresolved original check. Changed
timestamps, a new head without a repair diff, and unchanged unresolved relands
refuse. `CanonicalRunAdapter.correct` must authenticate actual diff/resolution
receipts and perform the current-generation compare-and-swap itself; a local
string or pure consistency check grants no authority. Closed or foreign items
remain subject to canonical lifecycle rules.

The expected graph is derived, never typed in. `derive_graph` reads the workflow
bytes at the merge revision and returns every job it declares: `name` templates
resolved per matrix leg (`${{ matrix.target }}`), unnamed matrix legs spelled as
the forge spells them (`job (a, b)`), and each `needs` expanded to every leg of
the job it names. The package has no YAML dependency, so the reader handles the
block-style subset a workflow uses for job identity and refuses by name
(`incident-original-run-graph-unsupported`) anything it cannot resolve with
certainty: a reusable-workflow job, matrix `include` / `exclude`, a dynamic
matrix, an expression other than `matrix.*` in a job name, a matrix job whose name
carries no `matrix.*` reference, an inline `{...}` mapping for a job or its
`strategy`, an unquoted matrix number YAML would print differently (`3.10`), or two
jobs that resolve to one name. A graph supplied by an operator is only checked against the
derived one: it is refused as `incident-original-run-graph-invalid`, naming the
jobs it omits or invents or whose `needs` differ, and a registered watched job
the workflow does not declare is refused the same way.

`OriginalRunWatcher` collects with no operator command. The controller service
starts it on a daemon thread; each tick (default sixty seconds) reads the
controller's own record and, once the recovery action for the registered landed
attempt is completed with a `recovery-inverse:<action id>:commit:<sha>` receipt
(any other receipt, a `rollback-conflict:` one included, landed no revert), takes
the revert to be the commit that receipt names, never a search of the branch. The
commit must be reachable from `origin/<branch>` of the reference clone and quote
the `Incident-Action: <action id>` trailer the inverse stamps on it, otherwise the
tick waits; a later commit that merely quotes the trailer cannot take its place.
It then runs the same `collect`. A run still in progress answers `in-progress` and the next
tick retries it until it is terminal. The record then carries
`original_run_collections[<action id>]` and later ticks do nothing. Ports, and so
the reference-clone fetch, are built only on a tick that owes a collection. All
durable state is the controller's record, so a restart resumes where it stopped;
a stop between recording the evidence and marking the collection is repaired by
the next tick, because the canonical `record` is idempotent by evidence digest and
the incident item keeps one record for the run.

The watcher is not silent. Each tick whose outcome differs from the previous one
(`waiting`, `refused`, `failed` or `collected`, with the refusal code or the
digest) is written to stderr as `incident-original-run-watch: <status>: <detail>`,
which the service unit sends to the journal, so a collection refused for good is
visible instead of retried unseen. A tick that cannot reach its inputs (`OSError`,
a subprocess failure or a `ValueError`) is named and retried at the next interval.
Any other error is a bug: it ends the watcher, the watcher calls the service's
shutdown, and the service exits non-zero so `Restart=on-failure` brings it back
instead of leaving a controller that answers HTTP and collects nothing. The
entrance names a merge tree the clone cannot read as
`incident-original-run-local-revision` rather than raising.

This slice does not provision canonical graph/repair authority, enable incident
CI, change a workflow or install fleet capability. The end-to-end proof, a real
reverted rehearsal incident on this repository that gets its evidence record with
no operator command, needs the running controller and a real reverted master run
and is captured on the host. At this source revision, the normal master workflow
already has no cancellation-on-new-push policy and its matrices retain
`fail-fast: false`; generated adopters still require their own verification.

## Running the entrance

`python -I -m livespec_dev_tooling.incident_original_run_entry` is the operator's manual
retry of what the watcher does by itself. It runs as the controller
account from the installed venv and takes `--config`, the protected `controller.json`.
It reads the state directory, repository, reference clone and canonical reader from
that verified installation, the tenant credential from `reader.env` beside it, and
reads the forge with the recovery App's read-only token. It needs no plugin registry,
credential wrapper or `gh`. A configuration that does not load as a protected
installation refuses as `incident-original-run-installation-unavailable`. It refreshes
the reference clone first, so a revert or corrected head already on the forge resolves.
The exact commands are in the module's docstring.

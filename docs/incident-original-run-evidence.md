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

This slice implements collection and canonical adapter seams. It does not
provision canonical graph/repair authority, schedule the controller, enable
incident CI, change a workflow or install fleet capability. Those integrations,
released serving adoption and end-to-end incident proof remain on carrier
livespec-dev-tooling-kobmka. At this source revision, the normal master workflow
already has no cancellation-on-new-push policy and its matrices retain
`fail-fast: false`; generated adopters still require their own verification.

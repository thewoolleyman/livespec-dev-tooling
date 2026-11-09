# Incident releases and installed consumer recovery

`IncidentReleaseRecovery` uses the independent observer's existing per-repository
record and lock. It retains the original canonical authority bytes, source/tag,
image digest, pin carrier, consumer revision and authenticated installation
receipt. These are immutable effect observations, not another attempt/phase
store. Canonical capabilities alone create lifecycle generations and corrective
work. Ordinary source green does not discharge installed consumer recovery.

The protected controller installation supplies `CurrentAuthorityReader` for
current admission and separate authenticated release capabilities. The artifact
verifier must resolve source membership in the **complete** canonical landed
commit chain, source-to-tag/image attribution, exact pin carrier, target consumer
and installation evidence. Comparing only the last incident SHA is insufficient.
Safe compensation for an irreversible change must already exist and be verified
by that capability; a caller's nonempty compensation string is not proof.

Release and pin dispatch entrances call `run_queued_adoption` immediately before
the actual effect. The distinct `verify_queued` capability authenticates the
source/tag/image, target revision and carrier before installation exists. This
first publication uses an empty installation receipt; it never fabricates a
future installed result. After observing actual installation,
`acknowledge_adoption` requires its independently verified receipt before the
canonical writer acknowledges adoption. The existing post-install verifier can
also validate an already-installed replay identity, but cannot authorize a first
publication without that separate queue capability.

Queued publication stores immutable intent before its callback and checks both
canonical current authority and the independent fence while holding the SAME
repository action lock as the observer. It rechecks immediately before effects,
including after a receipt lookup. Any retained recovery action or related
regression blocks stale queued adoption. The provisioned publisher is idempotent
by the supplied operation identity. It may not call this controller recursively.
After an exception, empty reply or unknown outcome, retry cannot call it again
without authenticated exact absence. A bound recorded lookup recovers the prior
receipt; wrong operation/identity, unknown, unavailable or malformed lookup stays
pending. No receipt is inferred from a label, timeout or arbitrary service text.

Canonical record, corrective work and reopen callbacks receive their immutable
payload and identity. Adapters must verify the service response binds the exact
operation and payload before returning a receipt, and must durably deduplicate
that identity. `ReleaseLookup` represents only such an authenticated service
answer. A missing lookup capability conservatively leaves unknown work pending.
The callback boundary does not provide a general shell command from incident
input, a writer credential, or a competing canonical parser.

The observer's existing persisted action fences adoption as soon as recovery
starts. Invoke `recover(intent=...)` **after** `handle_job_callback` and its inverse
callback return and release the repository lock. Calling it recursively inside
that callback would deadlock. Consumer reconciliation verifies the retained
exact inverse receipt and records one corrective operation per immutable
consumer attribution. Mutable observer bookkeeping such as `reconciled` cannot
create another correction. A late discovered consumer gets a new operation
without repeating work for consumers already assigned. Delayed installation
observations remain retained and fenced after revert rather than disappearing.

`reopen` retains related master, other-PR or consumer regression evidence and
fences cleanup. Its canonical capability authenticates attribution, reopens the
same incident chain if appropriate and invalidates stale cleanup ownership.
Historical corrective/reopen debt is still presented to the canonical owner
after another attempt changes the current registration. This module cannot
unilaterally reopen a lifecycle or let stale source adoption proceed. Known
external receipts are durably retained even if current authority changes before
the response arrives. Existing independent record fields are preserved.

This implementation is a source integration boundary, not installed capability.
Release-please, reusable release dispatch, image/plugin/wheel publication, pin
fan-out and installed consumer entrants still need normally released adapters
and serving adoption. The independently hosted controller must schedule receipt
and corrective-debt reconciliation after its inverse callback. Production
canonical release/history capabilities, scoped principals, protected serving
configuration and released consumer recovery drills remain rollout obligations.
No workflow policy is reduced, incident mode is not used to build this feature,
and factory/host proof is not manufactured by fixture callbacks.

## The release and pin dispatch screen

`POST /release/screen` is a read-only route of the observer, taking the query
credential (`incident_release_screen.py`). It reads only the controller's own
record and its independent reference clone. Its body is the exact
`{repository, source_sha, tag}` of one release, and it answers in one of three
ways:

- `refused` with `incident-release-recovery-retained`, in either of two cases:
  - the source commit or the tag is attributed (`release_attribution` or
    `release_adoption_intents`) to a registration that a retained recovery
    action or regression fences;
  - a recovery action that is not yet `completed` has a landed head that is an
    ancestor of the source.
- `refused` with `incident-release-source-unverifiable`, when the reference
  clone cannot decide that ancestry.
- `clear` otherwise. A record with no retained action is always clear.

A dispatch step runs the entrance `python -m
livespec_dev_tooling.incident_release_entry --observed-repository OWNER/REPO
--repository OWNER/SOURCE --source-sha SHA --tag TAG`. It reads
`LIVESPEC_INCIDENT_OBSERVER_URL` and `LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN`.

The entrance exits 0 with a no-op line, and makes no call, in two cases: when
the URL is unset, and when the source repository is not the observed one. A
dispatch with no incident observer therefore runs exactly as before.

Once configured, the entrance fails closed. A named refusal, an unreachable
observer, a misconfiguration or a malformed reply each exit 1 and name why.

Recorded residual: once a revert has completed, an unattributed release cut
from a pre-revert commit passes the screen, because the inverse receipt is
opaque to it.

The screen is not yet wired into `reusable-release-dispatch.yml` or
`reusable-bump-pin-from-dispatch.yml`. Both workflow edits, and the
reachability they need from GitHub-hosted runners, are tracked on
livespec-dev-tooling-wbvbj6.

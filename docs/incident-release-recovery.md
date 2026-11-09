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

### The observer route

`POST /release/screen` is a read-only route of the observer, taking the query
credential (`incident_release_screen.py`). It reads only the controller's own
record and its independent reference clone. Its body is the exact
`{repository, source_sha, tag}` of one release.

A **fence** is a recovery action (`actions`) or a regression
(`release_regressions`) retained against a registration. The route answers
in one of three ways:

- `refused` with `incident-release-recovery-retained`, in either of two cases:
  - the source commit or the tag is attributed (`release_attribution` or
    `release_adoption_intents`) to a fenced registration;
  - a fenced registration's landed head is an ancestor of the source, and no
    published inverse of it is.
- `refused` with `incident-release-source-unverifiable`, when the reference
  clone cannot decide one of those ancestries.
- `clear` otherwise. A record with no fence is always clear.

Only a `recovery-inverse:<action>:commit:<sha>` receipt proves a published
inverse, and it clears the head only for a source that contains that merge
commit. Each of these keeps a source holding the incident head refused:

- a pending action;
- a `rollback-conflict:` receipt, which completes the action without
  reverting anything;
- any other receipt;
- an inverse naming another action.

A regression is cleared only by a proven inverse recorded for the same
registration. The spec requires an attributable regression to trigger
recovery, and until an inverse is published, nothing has recovered it.

Because of this rule, a release cut from a commit before the revert stays
refused after the revert lands: it contains the incident head but not the
inverse.

### The dispatch entrance

A dispatch step runs:

```bash
python -m livespec_dev_tooling.incident_release_entry \
  --observed-repository OWNER/REPO --repository OWNER/SOURCE \
  --source-sha SHA --tag TAG
```

It reads two environment variables:

- `LIVESPEC_INCIDENT_OBSERVER_URL`, the observer's **base** URL. The entrance
  appends `/release/screen` to its path itself.
- `LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN`, the observer's query credential.

With no URL, the entrance prints a no-op line and exits 0 without any call. It
does the same for a source repository that is not the observed one. Once a URL
is set, it fails closed, and each of these exits 1 and names why:

- a named refusal from the observer;
- an unreachable observer;
- a malformed reply, or a reply past the 64 KiB bound;
- a misconfiguration: a URL that already ends in `/release/screen`, a
  non-https URL, a missing token, or an empty observed repository.

### Workflow wiring and its operator contract

Both reusable dispatch workflows now run the entrance:

- `reusable-release-dispatch.yml` runs it at the end of the
  `await-sandbox-image` job, AFTER the sandbox-image wait, so the verdict is
  fresh when `dispatch` fires. A refusal fails the job, and `dispatch` needs
  that job, so no sibling receives the release.
- `reusable-bump-pin-from-dispatch.yml` runs it before pin autodiscovery, from
  the `.livespec-dev-tooling` support checkout's environment. A consumer's own
  pinned dev-tooling may predate the entrance.

Each step resolves the tag to its peeled commit (`refs/tags/<tag>^{}`) and
falls back to the plain ref for a lightweight tag. Each step is skipped
entirely unless the caller sets the variable, so a repository that sets
nothing runs exactly as before.

| Caller setting | Kind | What it is |
| --- | --- | --- |
| `LIVESPEC_INCIDENT_RELEASE_SCREEN_URL` | repository variable | The observer's base URL, reachable from the job's runner. This is NOT the tailnet `LIVESPEC_INCIDENT_OBSERVER_URL` the incident CI job uses, because the dispatch jobs run on GitHub-hosted `ubuntu-latest`. |
| `LIVESPEC_INCIDENT_OBSERVED_REPOSITORY` | repository variable | The `owner/repo` that observer watches. The release side falls back to the caller's own repository. The pin side has no fallback. |
| `LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN` | repository secret | The observer's query token. It reaches the reusable workflow through the caller shim's `secrets: inherit`. |

Configuring the pin side has a trap. A consumer usually screens a SOURCE that
another repository's observer watches. If a consumer sets the URL but not
`LIVESPEC_INCIDENT_OBSERVED_REPOSITORY`, the pin step passes an empty observed
repository. The entrance refuses that by name. It does not pass in silence,
which is what it would do if the observed repository defaulted to the
consumer itself.

Enabling the screen still requires an observer route that GitHub-hosted
runners can reach. The observer is tailnet-only today, apart from
`/callback`. Each repository's shim pin must also be bumped to a release that
carries this wiring. Both steps are tracked on livespec-dev-tooling-wbvbj6.

# Complete incident inverse controller

Scope verification and patch construction read immutable objects through an
isolated Git administration directory. Source checkout diff settings, color,
order files, replacement refs and custom attributes cannot change the recorded
patch identity or select a merge driver. Linked worktrees retain their shared
object store and object format; the checkout, index and branch stay untouched.

`incident_inverse.plan_incident_inverse` validates a trusted forge scope's complete
landed commit chain, each landed tree, changed paths and full binary patch digest.
It reverses that entire patch into a disposable Git index seeded from the exact
current master head. Three-way application preserves later unrelated edits,
including later changes in the same file. Additions, deletions, binary content and
file modes are part of the inverse. The user's index, checkout and untracked
files remain untouched. A true overlapping edit is an owned rollback conflict,
never permission to restore whole parent files or discard descendant changes.

Construction uses private, template-free bare Git administration with the
source repository's object format and shared object database. Private
highest-precedence attributes select Git's built-in text merge without content
conversion. Repository merge drivers, `merge=union`, source `info/attributes`,
and system/global configuration cannot resolve a genuine overlap or execute a
driver. Conflicting binary content remains a conflict. Linked worktrees and
SHA-256 repositories retain their original object storage and format.

`recover_incident_inverse` runs inside the independent observer's repository
lock. The observer persists its immutable `RecoveryIntent` before calling it;
this function must not acquire that lock again. Recovery first looks up the exact
prior action receipt. The retained authority digest, repository and actual master
merge SHA must match the authenticated scope, and the scoped principal must
separately authorize the original armed PR/base/head and complete landed scope.
A pre-merge receipt with empty landed arrays is resolved through the authenticated
service, not treated as a single-commit rollback unit.

Publication uses an expected-master-head CAS. Only the explicit `head-moved`
result certifies no effect and permits recomputation, with the same immutable
action id, up to three attempts. A timeout, malformed response, unknown outcome or
missing exact effect receipt stays pending, and only an operator's explicit
`POST /reconcile` with `retry_publish` takes it further, through the principal's own
exactly-one ledger. No local validation, factory job,
pre-merge CI wait, retry of a flaky job or cancellation of the failed master run
is part of this path. Ordinary actors retain their normal protection policy.

`incident_inverse_service.ProcessInverseForge` is the adapter to the independently
installed, authenticated recovery principal. Its argv comes from the trusted
controller installation, never an incident tree, label, environment flag or tenant
wrapper. Each JSON request/reply carries integer `schema: 1`, the exact operation name and
a matching `binding.request_sha256` over the complete canonical request payload.
That digest includes the immutable action, repository, authority bytes, retained
arm and, for publication, the full inverse and expected head. A boolean schema,
a reply to another action, or an omitted binding is refused. The operations are:

| Operation | Required service behavior |
| --- | --- |
| `landed` | Authenticate retained observer arm and original PR/base/head; return complete landed chain, trees, binary patch SHA256 and changed paths. |
| `authorize` | Verify the immutable generation/owner grant and the narrowly provisioned recovery capability. |
| `head` | Read the authoritative repository branch head. |
| `lookup` | Recover the effect receipt for the exact action id, including a lost original reply. |
| `publish` | Durably reserve the action before effects, deduplicate that action across restart, compare master atomically, publish only the verified inverse tree through the scoped principal, and persist its exact receipt. |
| `conflict` | Persist rollback-conflict with its identified owner and exact action receipt before acknowledging it. |

## A conflict reaches the incident item's chain

The principal's `conflict` operation persists the owned rollback-conflict in the
recovery journal. The journal is the controller's own record and survives a tenant
outage, but it is not the incident item's lifecycle. `incident_conflict_chain.ConflictChain`
carries the journaled receipt onto the canonical chain through the orchestrator's
`record-rollback-conflict` action, called on the manifest's installed reader command
through the shared authority client (`incident_authority_client.call_authority`, the same
liveness ceiling and reply checks as every other reader caller). The writer runs only
when the manifest's reader release and command are approved, exactly as the other
readers require.

`record-rollback-conflict` accepts only a `reverting` generation, and a first master
failure has not reached it: the registration names the merged attempt
(`master-observation`). So the writer reopens first. For a first failure it calls
`reopen-regression` on the registration's own identity, with the registration's
canonical attempt record as the attributed attempt, the registration's owner as the
principal, and a `trunk` finding built from the failing leaf: the leaf's run id, its
failed head, the registration's landed commit as the attributed commit, and the recovery
action id as the subject, so the reopen is keyed to the same immutable action as the
revert. It then calls `record-rollback-conflict` on the `reverting` generation that
reply names. A regression reopen is already at `reverting` and is named directly, with
no second reopen. The conflict write takes `{receipt, release_condition}` as its payload
and writes the `rollback-conflict` phase at the next generation with the item's
lifecycle status `blocked`, keeping the identified owner.

Every payload field is a function of the journaled receipt and the registration, so a
repeat for the same action and head after a timeout or restart sends identical bytes and
the orchestrator recovers its one recorded transition. A repeat meets a reopen that is
already recorded, which the orchestrator refuses as `incident-reopen-stale-observation`
because the registration's identity is no longer the chain's current generation; the
writer then names the `reverting` generation that reopen produced (the orchestrator's
`recovery-<digest>` identity over the attempt and the finding) and the chain verifies it,
so a conflict write lost after a recorded reopen is finished by the next attempt.

A reply that does not prove the blocked `rollback-conflict` transition at the next
generation (a refusal, a timeout, an unavailable tenant) returns False after naming the
refusal on stderr, and changes no outcome: the conflict stays in the journal and is
replayed

- on every later `recover_incident_inverse` of the same action (a journaled conflict
  receipt is the "prior" the lookup returns), and
- by `POST /reconcile`, which marks the action `reconciled` only once the chain
  accepted the write, so an unreconciled conflict is retried on each reconcile.

Only a conflict receipt is ever replayed: a successful revert receipt never reaches the
conflict action.

A moved master head with no overlap recomputes the inverse and never writes the chain.
A registration still at the pre-merge `repair` phase is not reopenable; the orchestrator
refuses it as not eligible, the refusal is named on stderr, and the conflict stays
journaled until the chain has recorded the merge.

How the owner's resolution continues: nothing in dev-tooling moves a chain out of
`rollback-conflict`. The owner resolves the overlap and the orchestrator's
`resolve-rollback-conflict` action releases the chain, by the exact `release_condition`
this module wrote into the conflict record, back to `reverting` while the inverse is
still owed or on to `collecting-failures` once the resolution carries the revert
receipt. Re-running the inverse after a release is not part of this change: the
observer's `/recover` answers the registration's one existing immutable action, so
a released `reverting` generation does not start a second revert by itself.

`lookup` must distinguish `status: absent` (authoritative no effect) from
`status: recorded` (with its exact receipt) and reserved/unobservable state.
Only explicit bound absence returns `None`; an unavailable, malformed or reserved
lookup raises a refusal before any new publication. A restarted direct recovery
therefore cannot treat a lost lookup reply as no-effect authorization.

Byte fields, including the original canonical receipt and inverse patch, are
base64 in the process protocol. Complete immutable intent travels with every
scoped operation. The service's durable action reservation must make repeated
`publish` requests for one action id idempotent; a missing `lookup` receipt never
establishes that no effect occurred. The observer independently prevents a
pending callback from being replayed. Receipt reconciliation retains the original
canonical authority bytes and does not mint a replacement lifecycle generation.

The live recovery principal that answers this protocol is
`incident_recovery_principal_service.py` (`docs/incident-recovery-principal.md`).
It acts only as the dedicated recovery App. This adapter does not provision
that App's credential, the ruleset bypass, an independently hosted service,
release adoption or the controller installation. Those are normal rollout prerequisites. A process
fixture or real local Git CAS demonstrates mechanics, not deployed capability.
Live source recovery must remain disabled until those prerequisites and the
released-controller host proof are verified. The plan remains open for recovery
of installed consumers, failure collection, corrected attempts, normal factory
repayment and independent proof.

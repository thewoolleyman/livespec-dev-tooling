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
`record-rollback-conflict` action. It calls the manifest's installed reader command
through the shared authority client (`incident_authority_client.call_authority`), with
the same liveness ceiling and reply checks as every other reader caller. The writer
runs only when the manifest's reader release and command are approved. The recovery
itself never writes the chain. The controller service writes it afterwards, outside the
observer's repository lock (`docs/incident-observer-service.md`, "Rollback-conflict on
the chain").

`record-rollback-conflict` accepts only a `reverting` generation, and a first master
failure has not reached it, so the writer reopens first:

1. **Find the merged generation.** A standalone admission after the merge registers
   at `master-observation`, and that is the merged generation. A pre-merge arm stays at
   its `repair` generation: binding it to the master run after the merge changes no
   canonical identity, and that `repair` attempt is neither reopenable nor carrying
   landed commits. The orchestrator's `record-merge` writes `master-observation` one
   generation on, with the landed commits. So for a `repair` registration the writer
   reads that exact generation back with `read-history` (attempt `<attempt>`, operation
   `<attempt>#master-observation`, generation + 1; the same identity
   `_incident_original_run_canonical._merge_query` names). It uses the record only when
   it is this attempt's merge and its landed commits include the registration's master
   head.
2. **Reopen it.** The writer calls `reopen-regression` on the merged generation, with
   that generation's canonical attempt record as the attributed attempt and the
   registration's owner as the principal. The finding is a `trunk` finding built from
   the failing leaf: the leaf's run id, its failed head, the registration's landed
   commit as the attributed commit, and the recovery action id as the subject. That
   keys the reopen to the same immutable action as the revert.
3. **Record the conflict** with `record-rollback-conflict` on the `reverting`
   generation that reply names. A regression reopen is already at `reverting` and is
   named directly, with no second reopen.

The conflict write takes `{receipt, release_condition}` as its payload. It writes the
`rollback-conflict` phase at the next generation, sets the item's lifecycle status to
`blocked`, and keeps the identified owner.

Every payload field is a function of the journaled receipt and the registration, so a
repeat for the same action and head sends identical bytes. The orchestrator then
recovers its one recorded transition instead of adding a second. A repeat meets a
reopen that is already recorded, which the orchestrator refuses as
`incident-reopen-stale-observation`. The writer then names the `reverting` generation
that reopen produced: the orchestrator's `recovery-<digest>` identity over the attempt
and the finding.

Each write ends in one `ChainWrite`:

- `landed`: the reply proves the blocked transition.
- `retry`: the answer may change. Either the tenant was unavailable (the client's
  silence, or the orchestrator's own exit-78 `*-unavailable` refusal), the merge is not
  yet recorded, a claim move lost a race, or the refusal is not known to be final. The
  publication bounds every retry. A `claim-changed` that persists is the half-reopen
  named in `docs/incident-observer-service.md` ("Known limitation").
- `terminal`: the chain proved the write can never land. The owner already resolved it,
  a different reopen holds the chain, or a reply answers for another generation.

Only a conflict receipt is ever written: a successful revert receipt never reaches the
conflict action. A moved master head with no overlap recomputes the inverse and never
writes the chain.

How the owner's resolution continues: nothing in dev-tooling moves a chain out of
`rollback-conflict`. The owner resolves the overlap, and the orchestrator's
`resolve-rollback-conflict` action releases the chain by the exact `release_condition`
this module wrote into the conflict record. It releases back to `reverting` while the
inverse is still owed, or on to `collecting-failures` once the resolution carries the
revert receipt. A conflict the owner resolved before the writer reached it becomes
terminal (superseded) and is never written again.

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

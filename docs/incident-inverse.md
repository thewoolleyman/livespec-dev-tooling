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
missing exact effect receipt stays pending. No local validation, factory job,
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

# Protected recovery journal

`RecoveryJournal` retains effect reservations and owned conflict receipts for an
already authenticated observer recovery action. It uses the controller's
immutable `actions[action_id]` snapshot, including the original registration,
completion and arm. A newer top-level arm does not erase an older owed action.
The observer record is never changed by this journal.

The journal is the effect store of the independent recovery principal
(`docs/incident-recovery-principal.md`). That principal authenticates every
operation through `RecoveryJournal.lookup`, keeps its own per-action publication
record beside the journal, and writes the protected conflict context below after
proving a genuine overlap. This journal process, kept for compatibility, is no
longer the principal the manifest names. It supplies
no forge authorization, successful inverse publication or canonical lifecycle
transition. In particular, journal absence is an observation about one effect
store; it is not permission to publish. Actual scope authentication, signing,
credentials, exact-head publication and protection policy remain separate
prerequisites.

The installation provisioner must create two private directories beneath the
controller's existing protected state directory, both with mode 0700:

```text
<state>/recovery-journal/
<state>/recovery-journal-contexts/
```

The library takes the real observer repository fence before every reservation
or terminal write, then its distinct per-action journal lock. A call already
inside the observer's protected section borrows the verified live fence instead
of opening another conflicting lock. This also serializes standalone library
writes against observer completion. Point-in-time lookup does not create a new
terminal effect.

`ProcessInverseForge` passes the currently held lock descriptor to the fixed
journal process. The child validates the exact protected lock inode, ownership,
mode and same-open-file-description nonblocking lock, then borrows that fence
through persistence. The parent retains its lock until the synchronous child
returns or is killed and reaped. If the parent process crashes, the inherited
open file description continues to fence the live child. An ambient environment
marker alone confers nothing; the client scrubs it when no verified local fence
is held. Every conflict RPC requires that borrowed fence, including exact
retries. Missing or invalid inherited ownership refuses a conflict instead of
acquiring a substitute lock. A journal subprocess never calls the tenant or
credential wrapper or reads candidate-selected state configuration. Its paths and
identity come from the existing `ControllerInstallation` settings. The CLI
validates the entire protected installation using the existing public loader,
including its local secret-file integrity checks; it neither uses nor persists
those secret bytes.

The fixed approved argv uses an absolute installed script and positional
configuration after `--`, for compatibility with the installation manifest's
absolute-file policy:

```text
/opt/livespec-incident/venv/bin/python -I /opt/livespec-incident/venv/lib/python3.10/site-packages/livespec_dev_tooling/incident_recovery_journal_service.py -- /etc/livespec-incident/controller.json
```

The real provisioner supplies paths for its interpreter and installation; the
example does not select a Python release or install any service. The manifest
must authenticate every fixed file as usual. Invoking the CLI without isolated
Python or a valid protected installation refuses before reading a packet.

`ProcessInverseForge`'s existing schema-1 request/reply binding is preserved.
The journal's JSON codec uses only the Python standard library. It bounds raw
bytes and rejects duplicate keys, invalid UTF-8 and nonfinite numbers, including
exponent overflow, in both packets and protected records.
Only `lookup` and `conflict` RPCs are implemented. `reserve`, `publish`,
`authorize`, `landed` and `head` RPCs explicitly refuse before writing any
journal or context file. Reservation is a library operation for a future
independently authorized effect publisher; an unresolved reservation prevents
an uncertain prior effect from being treated as absence.

Exact retries preserve one canonical request and its result across restart.
JSON envelope whitespace and key order do not create another operation.
Conflicting bytes preserve the existing history. Corrupt or unreadable records
are unavailable; completed observer actions without a matching journal record
are also unavailable. An existing matching completed receipt can still be
recovered, but a completed action cannot gain a new terminal result.

Conflict persistence additionally requires a pre-existing protected context at
`<state>/recovery-journal-contexts/<action_id>.json`, mode 0600 or stricter:

```json
{"schema": 1, "request": {"intent": {}, "scope": {}, "expected_head": "...", "reason": "...", "receipt": "..."}}
```

The abbreviated objects above must contain the exact complete
`InverseConflictRequest` in the existing process wire format, including base64
byte fields. Scope identity must match the retained arm's PR/base/head and
registration merge/authority. The service derives and validates the receipt
`rollback-conflict:<action>:owner:<owner>:head:<head>`; arbitrary caller text or
request checksums cannot establish a genuine conflict.

This source does not provide the independent forge-scope verifier that produces
that context. It never writes a context from an RPC. Missing or unverifiable
context refuses a terminal conflict receipt. Controlled protected context
fixtures demonstrate persistence and retry mechanics, not production forge
authority, account separation, deployment or plan Proof of Done.

All records use atomic replacement and file/directory fsync before success is
returned. A lost reply recovers the original non-authorizing result instead of
inventing a new lifecycle generation. Every response explicitly keeps
`authorizes_current_effects` false. Normal release, independent installation,
the actual principal capability and hosted incident/recovery drills remain
required before incident activation.

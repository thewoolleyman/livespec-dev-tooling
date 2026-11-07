# Live incident recovery principal

`incident_recovery_principal_service.py` is the independently provisioned
recovery principal that `incident_inverse.recover_incident_inverse` calls
through `ProcessInverseForge` (`docs/incident-inverse.md`). The incident
observer's released-installation manifest names it in place of the journal-only
service. It is the one component that moves `master` for an incident, and it
does so only as a **dedicated recovery GitHub App**. Work item
`livespec-dev-tooling-7536jf`, plan `expedited-incident-response-flag`.

```text
<interpreter> -I <installed incident_recovery_principal_service.py> <controller.json>
```

## Identity and credential

The recovery App is separate from the fleet factory and publishing bot
(`GITHUB_APP_ID` / `GITHUB_PRIVATE_KEY`). Master's ruleset names only this App
as a bypass actor. That bypass is the whole capability: it lets the exact
inverse reach `master` without waiting for required checks. A bypass exempts an
actor only from the ruleset that grants it, so `ci-green` is required by that
ruleset and no longer by classic protection, which still enforces admins. Every
other actor is judged as before. The principal never switches protection off and
never fakes a green check.

The principal reads the credential from `recovery-app.json`, which sits next to
the protected `controller.json`. The file holds `{"app_id": "<digits>",
"private_key": "<PEM>"}`, has mode 0600 and is owned by the controller account.
The incident_observer role writes it at apply, under `no_log`, from
`LIVESPEC_RECOVERY_APP_ID` and `LIVESPEC_RECOVERY_APP_PRIVATE_KEY`. The credential
wrapper projects those two values on the control node. The key is never stored in
this repository or in an environment variable of the observer or its reader.

The credential is read lazily. `lookup` and `conflict` still answer for an
action with no open publication while the App is unprovisioned. Every operation
that needs the forge refuses by name instead:

| Refusal code | Meaning |
| --- | --- |
| `recovery-app-credential-absent` | No projected `recovery-app.json` (the state until the maintainer's GO-1). |
| `recovery-app-credential-unprotected` | The file is a symlink, not a regular file, not owned by this account, or group/other accessible. |
| `recovery-app-credential-malformed` | The file does not hold exactly a numeric `app_id` and a PEM `private_key`. |
| `recovery-app-signing-unavailable` | `/usr/bin/openssl` could not sign the App JWT. |
| `recovery-app-not-installed` | The App's installation does not cover the observed repository. |
| `recovery-app-token-refused` | GitHub minted no token on that one repository whose grant is `contents: write`, alone or with the `metadata: read` GitHub adds to every App token. Any other read or write is refused. |

Each process mints one installation token. The token is scoped to the observed
repository with `contents: write` only and is never written to a reply, record
or log. Every REST call goes through the budgeted client, against the fixed API
origin that `budgeted_gh.github_api_url` owns.

## The six operations

The envelope is exactly the one `ProcessInverseForge` sends: integer
`schema: 1`, the operation name, and `binding.request_sha256` over the canonical
payload. `publish` and `conflict` require the observer's borrowed repository
fence, as the journal's `conflict` does. Every operation re-authenticates the
exact retained action through the protected journal before it does anything
else.

| Operation | What the principal does |
| --- | --- |
| `landed` | Reads the armed pull from the forge and requires `merged`, `merge_commit_sha` equal to the registered master SHA, base ref `master`, and head equal to the arm's head. It fetches master into the reference clone and derives the first-parent chain of the pull's commit count. It requires that chain's messages to equal the pull's own commit messages in order, which is what a rebase merge produces. It returns the complete chain, trees, full binary patch digest and changed paths only when `scope_matches_git` verifies them. |
| `authorize` | Requires a pending action with no recorded effect and a scope bound to the retained grant. It authorizes only when the forge-derived scope equals the scope it was given. |
| `head` | Reads master's head from the forge and fetches it into the reference clone. |
| `lookup` | See "Exactly one revert per action" below. |
| `publish` | Re-derives the scope, reads the forge's current head, and recomputes the inverse itself. It refuses any request that is not exactly that inverse. If master moved, it answers `head-moved` with no effect, and the observer recomputes with the same immutable action. |
| `conflict` | Requires that no publication exists and that the scope is the forge's scope. It then recomputes against the request's head and requires a genuine three-way `rollback-conflict`. Only then does it write the independently authenticated context that `RecoveryJournal.record_conflict` demands, and it records the owned conflict. |

## Publication: one effect, verified before it happens

1. A `reserved` attempt is saved durably before any forge call.
2. The principal creates the inverse tree through the Git Data API. Text blobs
   go inline and binary blobs are uploaded. The tree the forge returns must have
   the same SHA as the tree computed locally. If it does not, the attempt is
   `abandoned` and the principal refuses.
3. The revert commit is created with a single parent, the expected head. Its
   SHA is saved and the attempt becomes `prepared`. Master has not moved yet.
4. A non-forced ref update moves master to that commit. It succeeds only as a
   fast-forward. Because the commit's only parent is the expected head, a master
   that has moved refuses the update with no effect. Master's protection forbids
   rewinding master to an ancestor, so the fast-forward is an expected-head
   compare-and-swap.

No local test, factory run, pre-merge CI or check wait is on this path.

## Exactly one revert per action

The publication record is `<state>/recovery-journal/<action>.publication.json`.
It is held under a per-action lock and written with the observer store's atomic
replace and fsync. It keeps every attempt. At most one attempt is open
(`reserved` or `prepared`), and the merge receipt is final once recorded.

- A repeated `publish`, after a timeout, a lost reply or a restart, first
  resolves the open attempt from forge facts. If the recorded commit is on
  master, the principal records it and returns the original receipt. If master
  still sits at the expected head, it sends the same commit again. If master
  moved past it, the attempt is `head-moved`. A `reserved` attempt with no
  commit never sent a ref update, so it is `abandoned`. No path creates a
  second revert commit.
- `lookup` answers `absent` only for a pending action that has no open attempt
  and no journal effect. It answers `recorded` with the receipt
  `recovery-inverse:<action>:commit:<sha>` once the revert landed, and the
  journal's owned conflict receipt after a conflict. It answers `reserved`
  while an earlier attempt may still have landed. `ProcessInverseForge` raises
  on `reserved`, so the observer stays pending and publishes nothing new. A
  damaged record or observer state is a refusal, never an absence.

## What the tests prove, and what needs the host

`tests/livespec_dev_tooling/test_incident_recovery_principal*.py` use a bare
Git repository that answers the REST subset with real blobs, trees, commits and
a real fast-forward check. The observer's real `ProcessInverseForge` and
`recover_incident_inverse` are answered in process by this principal. Those
tests cover the exact merge, recomputation on a moved head, the owned conflict,
idempotent publication after a lost reply or an interrupted update, and every
refusal.

They do not prove deployed capability. Applying the role on the observer host,
the real App installation and token, the ruleset bypass, and a real merge of an
inverse are host-captured evidence for the plan's live sequence (note 006,
phase 3). Provisioning the App, its 1Password key and the ruleset is the
maintainer's step GO-1 (role README, maintainer step 4).

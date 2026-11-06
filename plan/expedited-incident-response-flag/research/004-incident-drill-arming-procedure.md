# Incident drill: arming procedure and block text (read-only research, not yet executed)

Status when committed (2026-11-06, about 13:40Z): blocker B3 below is cleared, the coordinator created the label
`expedited-incident-response` on the repository. Blocker B2 is owned by `livespec-dev-tooling-truk55`, which the
plan owner moved onto the critical path as a hand lane (coordinator: no objection, 13:34Z). The procedure has NOT
been run; treat every INFERRED line as unproven until the drill.

Researched 2026-11-06 13:05Z to 13:40Z on host `vps` (this host; its local clock is CET, every time below is UTC).
Nothing was written to a ledger, repository, service or host. Reads that needed `sudo` were limited to the
non-secret manifest, `controller.json`, the state directory listing, the reference clone and the unit journal.

Marking: **VERIFIED** = read in the released code or measured with a read-only command (file:line or command given).
**INFERRED** = follows from verified facts but was not exercised.

Released bytes used as the source of truth:

- Controller: `livespec-dev-tooling` **v1.183.1** (commit `580feacaa572b00d990ab568687d61c1ef512f9c`), the release the
  observer serves. `git diff v1.183.1 HEAD -- livespec_dev_tooling` and `v1.183.1..v1.184.0` show no change to any
  incident module, so master line numbers below equal the released ones. VERIFIED.
- Reader: orchestrator **v0.295.1** (commit `e4389633e1ebc0ef7400d9df4d4212d792b3199e`). Paths below are relative to
  `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/` at that tag unless they start with `bin/`.
  The dev-tooling project's registered plugin build is the same commit
  (`~/.claude/plugins/cache/livespec-orchestrator-beads-fabro/livespec-orchestrator-beads-fabro/e4389633e1eb`), and its
  `scripts/bin/incident_authority.py` has the same SHA256 as the observer's copy. VERIFIED.

---

## 0. Blockers first: what cannot work today

| # | Finding | State now | Evidence |
|---|---|---|---|
| B1 | **The incident item must live in the `livespec-dev-tooling` tenant, not `bd-ib`.** The observer runs its reader as `read-current --repo /var/lib/livespec-incident/reference ...`, and the reader resolves its tenant from that `--repo`. The reference clone is dev-tooling at v1.183.1 and names tenant and database `livespec-dev-tooling`. | A `bd-ib` item is unreadable there. Reproduced with the installed reader: `read-current --repo /data/projects/livespec-dev-tooling --item bd-ib-dzbwaq` answers `incident-authority-unavailable` ("no issue found matching bd-ib-dzbwaq"), exit 78. `/arm` would answer 403 `canonical pre-merge authority unavailable`. | `livespec_dev_tooling/incident_observer_authority.py:38-53`; `incident_observer_control.py:108-114`; orchestrator `commands/incident_authority.py:96`, `commands/_config.py:203-239`; reference clone `.livespec.jsonc:189-197` (read with sudo); VERIFIED |
| B2 | **Genesis for a dev-tooling item needs the dev-tooling tenant cut over, which has not started.** `publish-genesis` reads `dispatcher.claim_tokens` from the `.livespec.jsonc` of the `--repo` it is given (working tree, default `false`) and then requires the item to name an open claim token. | Key absent on dev-tooling origin/master and in the primary (0 matches). Survey `migrate_claim_tokens.py --project-root /data/projects/livespec-dev-tooling` (no confirm flag, writes nothing): **305 non-closed items name no open token, 0 name one**, exit 1. The owning item is `livespec-dev-tooling-truk55`, status `blocked`, `blocked-reason:needs-human`. The orchestrator cutover (bd-ib-4eeefv) does not change any of this. At 13:22Z the orchestrator key was itself not yet on origin/master. | orchestrator `commands/incident_authority.py:132-156`, `commands/_dispatcher_policy_settings.py:318-325,355-368`, `effects/_incident_genesis_writer.py:86-98`; `SPECIFICATION/contracts.md:7998-8012`; VERIFIED |
| B3 | **The repository label `expedited-incident-response` does not exist.** The released entrance takes the incident path only for a PR that carries it; with the block and no label the incident-ci job fails ("selected the 'normal' mode"). | `gh api repos/thewoolleyman/livespec-dev-tooling/labels/expedited-incident-response` answers 404; the repository has 12 labels, none matching. | `incident_ci_entry.py:41`, `incident_ci_event.py:66`, `_incident_ci_types.py:65`, `.github/workflows/ci.yml:912-915`; VERIFIED |
| B4 | **Only one observer exists and it serves `thewoolleyman/livespec-dev-tooling`.** The orchestrator repository has no incident-ci job, so "the drill on the orchestrator tenant" has no CI entrance and no observer. | `controller.json` `repository`; `grep incident-ci` over the orchestrator workflows finds nothing. | VERIFIED |

`bd-ib-dzbwaq` is **not** a dependency of the arm path. Everything the path uses (`publish-genesis`, `commit-transition`,
`read-current`) ships in v0.295.1. What dzbwaq still owes is the canonical entry verb and the fencing of a live factory
claim, so the path depends on it in exactly one case: genesis refuses `incident-factory-fence-unavailable` for an item
that is `active` with assignee `fabro` (`effects/_incident_genesis_writer.py:91-92`). Choose an item that is not.
VERIFIED (item read 13:15Z: `ready`, its 01:13Z comment says the same).

Consequence: the procedure in section 1 is the sanctioned path and is executable only after B2 and B3 are cleared.
Section 6 lists two non-sanctioned shapes the code would also accept, for the lead's information only.

---

## 1. Ordered operator steps (one item, one PR)

Conventions. `REPO=/data/projects/livespec-dev-tooling` (primary, on master, pulled after the cutover commit).
`IA="python3 <registered plugin root>/scripts/bin/incident_authority.py"`; resolve the root with
`registered_plugin_root.py --repo $REPO` (`.ai/stale-plugin-build-path.md`). Every `bd` and `incident_authority.py`
call runs under `/usr/local/bin/with-livespec-env.sh --`. `H=` the helper
`plan/expedited-incident-response-flag/research/004-incident-arm-helper.py.txt` (copy it to a `.py` file outside the repository to run it)
(stdlib only, prints JSON, calls nothing). Its output was checked against the released decoders of both
repositories with fictitious values: the genesis request decodes, the successor is canonical and a valid transition,
the arm id equals the one the observer computes, the block decodes and yields the same six-field query. VERIFIED
(offline, no ledger or network).

Identities that exist, and where each comes from:

| Identity | Value | Source |
|---|---|---|
| `repository` | `thewoolleyman/livespec-dev-tooling` | must equal controller.json `repository` (`incident_observer_service.py:92`) |
| `item_id` / `incident_item_id` | one `livespec-dev-tooling-*` item, non-closed, not `active`+`fabro`, naming an open claim token | B1, B2 |
| `attempt_id`, `owner`, `principal` | free text, nonempty, trimmed (operator's choice, for example `drill-1`, `human:thewoolleyman`, the session name) | `_incident_authority_payload.py:103-114`, `_incident_genesis.py:133` |
| `operation_id` | free text, **unique per generation in the chain** | `effects/_incident_authority_reader.py:116-117` |
| `generation` | 1 at genesis, exactly +1 per transition | `_incident_genesis.py:115`, `effects/_incident_authority_transition.py:64` |
| `phase` | `repair` (the only phase `/arm` accepts) | `incident_observer_admission.py:56` |
| `expected_claim` | the item's `metadata.dispatch_claim_token` as read now | `_incident_genesis.py:66-71` |
| tokens | root token (closed at genesis), open successor incident token, closed claim token, successor claim token | `effects/_incident_genesis_writer.py:126-178` |
| `authority_receipt` | bytes of `json.dumps(result.attempt, sort_keys=True, separators=(",", ":"))` from `read-current`, hex-encoded on the wire | `incident_observer_authority.py:71-75` |
| `arm_id` | SHA256 of the 14-key arm snapshot (section 2) | `incident_observer_admission.py:65-67` |

### Step 1. Preconditions (stop if any fails)

1. dev-tooling tenant cut over: `grep -n claim_tokens $REPO/.livespec.jsonc` shows `true` in the working tree, and the
   survey above exits 0.
2. The item: `bd show <ITEM> --json` shows a non-closed status, not (`active` and assignee `fabro`), and a nonempty
   `metadata.dispatch_claim_token`. Keep it out of dispatch for the drill's length (INFERRED: a dispatch would make it
   `active`/`fabro` and rotate its claim token).
3. Label `expedited-incident-response` exists in the repository.
4. Observer state: no retained arm today (state directory holds only the `.lock` file). If a record exists by then,
   its arm id is needed as `expected_arm_id` and its generation is a floor (section 4).
5. Host latency: see R1 in section 6. Run the timing probe there first.

### Step 2. Reserve the branch (no ledger write yet)

In a worktree on a new branch from master, stage the drill change, then read the boundary:

```bash
INPUT_PARENT=$(git rev-parse HEAD)          # the master commit the branch starts from
STAGED_TREE=$(git write-tree)               # tree of the staged index
TARGET_REF=refs/heads/<branch>
CLAIM=$(bd show <ITEM> --json | python3 -c 'import json,sys; d=json.load(sys.stdin); d=d[0] if isinstance(d,list) else d; print(d["metadata"]["dispatch_claim_token"])')
```

### Step 3. Publish genesis (LEDGER WRITE, dev-tooling tenant)

```bash
python3 $H genesis-request --repository thewoolleyman/livespec-dev-tooling --item <ITEM> \
  --attempt <ATTEMPT> --operation <OP1> --owner <OWNER> --principal <PRINCIPAL> \
  --expected-claim "$CLAIM" --target-ref "$TARGET_REF" --input-parent "$INPUT_PARENT" \
  --staged-tree "$STAGED_TREE" --path <repo-relative path changed> [--path ...] > genesis.json

/usr/local/bin/with-livespec-env.sh -- $IA publish-genesis --repo $REPO \
  --repository thewoolleyman/livespec-dev-tooling --item <ITEM> --attempt <ATTEMPT> \
  --phase repair --operation <OP1> --generation 1 --owner <OWNER> \
  --genesis-json "$(cat genesis.json)"
```

- Request shape: exactly `schema` 1, `principal`, `expected_claim`, `attempt`, as canonical bytes (sorted keys,
  compact separators). The attempt has all 16 keys: `repository, item_id, attempt_id, phase, operation_id, generation,
  owner, base, head, pr_number, landed_commits, landed_trees, original_paths, deferred_work, repayment_required,
  carrier`; generation 1, phase `repair`, `pr_number` 0, empty landed lists, a nonempty `original_paths`, carrier
  `{"state":"branch-reserved","target_ref","input_parent","staged_tree"}`. The CLI's `--attempt/--owner/--generation/
  --phase` must equal the request's. VERIFIED (`_incident_genesis.py:48,110-142`, `_incident_authority_payload.py:117-187`,
  `commands/incident_authority.py:132-146`). The helper sets `base` and `head` to the input parent, because no commit
  exists yet and the decoder only requires two object ids; INFERRED choice.
- What it writes, in order: two incident tokens (root, successor), one successor claim token, closes the root with the
  generation-1 transition, closes the item's current claim token with the genesis fence reason, appends the
  `livespec-incident-authority-v1` comment (five keys, including `claim_token_id`), rewrites the item's metadata to name
  the successor claim token. Lifecycle status is not changed. VERIFIED (`effects/_incident_genesis_writer.py:117-178`).
- Receipt (stdout, exit 0): `{"schema":1,"status":"verified","authorizes_current_effects":false,"normal_factory_proof":false,
  "result":{request_digest, root_token_id, claim_token_id, successor_claim_token_id, committed_token_id,
  current_token_id, attempt, recovered}}`. A refusal exits 78 with `result.code`. VERIFIED (`_incident_genesis.py:88-99`,
  `commands/incident_authority.py:173-191`).
- Retry: the same command with byte-identical `--genesis-json` recovers the original receipt (`recovered: true`);
  changed bytes under the same operation refuse `incident-operation-conflict`. The publish runs inside a 120 s lease.
  Keep `genesis.json`. VERIFIED (`effects/_incident_genesis_recovery.py:76-100`, writer `:164-165`).

### Step 4. Commit, push, open the pull request (normal gates, no incident flag)

Commit the staged tree unchanged (check `git rev-parse HEAD^{tree}` equals `$STAGED_TREE` and `HEAD^` equals
`$INPUT_PARENT`; a hook autofix changes the tree), push, open the PR from a branch of the same repository (a fork head
is refused, `incident_ci_event.py:73`). The first CI run is an ordinary one: the body has no block yet. Then read the
PR from the forge:

```bash
gh api repos/thewoolleyman/livespec-dev-tooling/pulls/<N> --jq '[.number,.base.sha,.head.sha]'
```

The released code does not enforce the git side (it "models and validates the state only", orchestrator
`docs/incident-authority.md` "Carrier state"); the spec does require it (`SPECIFICATION/contracts.md:10890-10894`).

### Step 5. Bind the PR: one transition to generation 2 (LEDGER WRITE)

```bash
/usr/local/bin/with-livespec-env.sh -- $IA read-current --repo $REPO --repository thewoolleyman/livespec-dev-tooling \
  --item <ITEM> --attempt <ATTEMPT> --phase repair --operation <OP1> --generation 1 --owner <OWNER> > gen1.json
python3 $H successor --operation <OP2> --pr-number <N> --base-sha <BASE> --head-sha <HEAD> < gen1.json > successor.json
/usr/local/bin/with-livespec-env.sh -- $IA commit-transition --repo $REPO --repository thewoolleyman/livespec-dev-tooling \
  --item <ITEM> --attempt <ATTEMPT> --phase repair --operation <OP1> --generation 1 --owner <OWNER> \
  --successor-json "$(cat successor.json)"
```

- The identity flags name the **prior** attempt (generation 1, `<OP1>`); the successor is the full attempt as canonical
  JSON with `generation` 2, a new `operation_id`, `pr_number` N, `base`/`head` from the forge read, and carrier
  `pr-bound` keeping `target_ref`, `input_parent`, `staged_tree` and adding `remote_head`. VERIFIED
  (`commands/incident_authority.py:110-124`, `effects/_incident_authority_transition.py:60-73`, `_incident_carrier.py:125-145`).
- `commit-transition` needs no `claim_tokens` check and writes one token plus one conditional close. Its reply is an
  `IncidentReading` with `authorizes_current_effects: false`; an exact retry recovers it. VERIFIED (`:104-132`).
- The spec's path is three states (`branch-reserved`, `head-published`, `pr-bound`), three generations. The released
  validator also accepts the direct step used here (rank 0 to 2). **Use the direct step**: every extra generation adds
  about 1.07 s to each reader pass, against a 10 s limit (R1). Spec and code disagree here; the code is what runs.
- Once `pr-bound`, the chain can never name another PR number (`_incident_carrier.py:145`).

### Step 6. Read the current authority and build the arm

```bash
/usr/local/bin/with-livespec-env.sh -- $IA read-current --repo $REPO --repository thewoolleyman/livespec-dev-tooling \
  --item <ITEM> --attempt <ATTEMPT> --phase repair --operation <OP2> --generation 2 --owner <OWNER> > gen2.json
python3 $H arm --controller-release v1.183.1 --controller-revision 580feacaa572b00d990ab568687d61c1ef512f9c \
  --required-job ci-green < gen2.json > arm-out.json
python3 -c 'import json; d=json.load(open("arm-out.json")); json.dump(d["arm_request"], open("arm-request.json","w"))'
```

`gen2.json` must say `status: verified`, `authorizes_current_effects: true`, `result.is_current: true`.
The three host values are the manifest's (`/etc/livespec-incident/released-installation.json`, read 13:12Z):
`release` `v1.183.1`, `revision` `580feacaa572b00d990ab568687d61c1ef512f9c`, `required_jobs` `["ci-green"]`,
`reader_release` `v0.295.1`. VERIFIED. They change with the next role apply that moves the release; re-read them.

### Step 7. `POST /arm`

- URL: `https://vps.perch-rudd.ts.net:8765/arm` (tailnet only; the listener is `127.0.0.1:8765` on `vps`).
- Headers: `Authorization: Bearer <control secret>`, `Content-Type: application/json`.
- The control secret is `LIVESPEC_INCIDENT_CONTROL_SECRET` inside `/usr/local/bin/with-livespec-env.sh` (present,
  64 characters). The query secret is `LIVESPEC_INCIDENT_QUERY_SECRET`. VERIFIED by length only.
- Body: exactly these 11 keys, plus the optional `expected_arm_id` (omit it for the first arm; today there is none):

```json
{
  "repository": "thewoolleyman/livespec-dev-tooling",
  "incident_item_id": "<attempt.item_id>",
  "attempt_id": "<attempt.attempt_id>",
  "operation_id": "<attempt.operation_id (OP2)>",
  "generation": 2,
  "owner": "<attempt.owner>",
  "phase": "repair",
  "pr_number": 0,
  "base_sha": "<attempt.base>",
  "head_sha": "<attempt.head>",
  "authority_receipt": "<hex of the canonical attempt bytes>"
}
```

  (`pr_number` is the real positive PR number as a JSON integer; `generation` is an integer.) Any extra key, a missing
  key or a wrong type answers 403 `invalid control request or unavailable protected state`; sending
  `controller_release`, `controller_revision` or `required_jobs` answers 403 `controller identity and job universe
  belong to host provisioning`. VERIFIED (`incident_observer_control.py:81-107`, `_incident_observer_store.py:143-177`,
  `incident_observer_service.py:86-123`).

```bash
/usr/local/bin/with-livespec-env.sh -- bash -c \
 'printf "header = \"Authorization: Bearer %s\"\n" "$LIVESPEC_INCIDENT_CONTROL_SECRET" |
  curl -sS --config - --max-time 30 -o arm-reply.json -w "%{http_code}\n" -X POST \
       -H "Content-Type: application/json" --data-binary @arm-request.json \
       https://vps.perch-rudd.ts.net:8765/arm'
```

  The `printf` is a shell builtin, so the secret reaches neither an argv nor the output. This exact command line was
  NOT run (no POST was allowed); INFERRED.
- What the observer does: adds the three host fields, runs the reader (`read-current` over the retained identity,
  10 s limit), requires the reply's attempt to equal the receipt bytes and to name the same PR, base and head, requires
  phase `repair` and `head_sha` different from the controller revision, then stores the arm. VERIFIED
  (`incident_observer_control.py:93-124`, `incident_observer_authority.py:35-81`, `incident_observer_admission.py:54-94`).
- Success: HTTP 202 `{"status":"armed","reason":"durable observer ready for this exact PR before merge","action_id":null,
  "receipt":"<arm_id>"}`. The `receipt` must equal `arm-out.json` `expected_arm_id`. Repeating the same request answers
  `same durable pre-merge arm`. Refusals are HTTP 403 with a `reason`; `canonical pre-merge authority unavailable`
  covers a reader failure, a reader timeout and any identity or receipt mismatch alike.

### Step 8. Label and body block, then one CI run on the unchanged head

1. Add the label `expedited-incident-response` to the PR.
2. Put the block (section 2) in the PR body with the API or `gh pr edit <N> --body-file` (LF line endings).
3. Check: `gh api repos/thewoolleyman/livespec-dev-tooling/pulls/<N> --jq .body` contains no carriage return, exactly one
   `<!-- livespec-incident-ci` line and exactly one line that is only `-->`.
4. Start a run without moving the head. The workflow triggers on the default `pull_request` types (`ci.yml:96-99`), so a
   label or body edit starts nothing: close and reopen the PR. Re-read `.base.sha` and `.head.sha` afterwards; if either
   moved, the arm no longer matches and steps 5 to 7 repeat with generation 3 and `expected_arm_id`.

Any push to the PR changes `head_sha` and has the same effect.

---

## 2. The `livespec-incident-ci` block

Parser: `livespec_dev_tooling/incident_ci_event.py:15-17` (markers and the 16384-byte bound), `:65-79` (extraction),
then `incident_ci_payload.py:39-78` (`decode_authority`). Workflow prefilter: `.github/workflows/ci.yml:870`
(`grep -qE '^<!-- livespec-incident-ci[[:space:]]*$'`). VERIFIED.

```text
<!-- livespec-incident-ci
{"schema":1,"arm":{"repository":"thewoolleyman/livespec-dev-tooling","incident_item_id":"<ITEM>","attempt_id":"<ATTEMPT>","operation_id":"<OP2>","generation":2,"owner":"<OWNER>","phase":"repair","pr_number":<N>,"base_sha":"<BASE 40 hex>","head_sha":"<HEAD 40 hex>","required_jobs":["ci-green"],"controller_release":"v1.183.1","controller_revision":"580feacaa572b00d990ab568687d61c1ef512f9c","authority_receipt":"<hex>"},"observer_arm_id":"<64 hex>"}
-->
```

Rules the released parser applies:

- Begin marker is exactly `<!-- livespec-incident-ci` followed by a line feed; end marker is a line feed followed by
  `-->`. The body must contain each **exactly once**, so no other HTML comment in the body may end with a line that
  starts with `-->`. A body with CRLF line endings (a web-UI edit) is refused: checked against the released parser,
  it returns no payload. VERIFIED (`incident_ci_event.py:69-75`).
- The payload between the markers is one JSON object with exactly the root keys `schema` (integer 1), `arm`,
  `observer_arm_id`; duplicate keys refuse; at most 16384 bytes. Key order and whitespace inside the JSON do not matter.
- `arm` has exactly 14 keys: the 11 of the `/arm` body plus `controller_release`, `controller_revision`,
  `required_jobs` (the host manifest's values). `generation` and `pr_number` are integers, `required_jobs` a list of
  strings, `authority_receipt` the hex string. VERIFIED (`_incident_observer_store.py:155-177`).
- `observer_arm_id = sha256(json.dumps(arm, sort_keys=True).encode()).hexdigest()` with Python's **default**
  separators (`", "` and `": "`), not the compact form. It equals the `receipt` `/arm` returned. VERIFIED
  (`incident_ci_payload.py:51-53`, `incident_observer_admission.py:65-67`).
- The PR must also carry the label, be open, have its head in the same repository, and its forge-read number, base
  and head must equal the arm's. VERIFIED (`incident_ci_event.py:37-51,66,73`, `incident_ci_policy.py:58-75`).
- The block is a consistency packet, not authority: the job then asks the observer.

The helper prints the finished block as `pr_body_block` in `arm-out.json`.

Docs against code: `docs/incident-ci-entry.md` still says the workflow entrance is not installed and that no producer
of the packet exists. The entrance is installed (`ci.yml:794`); there is still no producer command, which is why the
helper exists. The block text and the id rule in that document match the code.

---

## 3. `/current` and `/admitted`, and a second pull request

Both are `POST` with `Authorization: Bearer <query secret>` and a JSON body of exactly six fields
(`incident_observer_query.py:23-25,83-97`; client side `incident_ci_authority.py:43-103`):

```json
{"repository":"thewoolleyman/livespec-dev-tooling","arm_id":"<64 hex>","pr_number":<N>,
 "base_sha":"<40 hex>","head_sha":"<40 hex>","receipt_digest":"<sha256 of the authority receipt BYTES, 64 hex>"}
```

`receipt_digest` is the SHA256 of the raw receipt bytes (the hex string decoded), `incident_ci_payload.py:74`.

A 202 answer has exactly three keys, `Content-Type: application/json`, `Cache-Control: no-store`:

```json
{"schema": 1, "status": "current", "query": { ...the six fields echoed... }}
{"schema": 1, "status": "admitted", "query": { ...the six fields echoed... }}
```

- `/admitted` checks only the retained arm under the repository lock: same arm id, not bound, not invalidated, same
  repository, PR, base, head and receipt digest. It makes no ledger read. VERIFIED (`incident_observer_query.py:63-80`).
- `/current` does that, then runs the reader against the ledger, then re-checks the arm. A reader failure or timeout
  answers 403 `canonical authority stale, unavailable or arm changed`. VERIFIED (`:46-56`).
- Neither read changes the record, so any number of CI runs on the **same** PR, base and head are admitted while the
  arm stands. The CI entrance asks both at plan, before each real member and twice at the aggregate
  (`incident_ci_entry.py:87-90,123-138`). With two fast members that is about five `/current` calls per run. VERIFIED
  for the code, INFERRED for the count.

**A second PR against the same armed incident is not admitted.** VERIFIED:

- The observer keeps one arm per repository (one record file, one `observer_arm`; `_incident_observer_store.py:53`,
  `incident_observer_admission.py:82-88`), and a query must match its exact PR, base and head.
- The incident chain cannot move to another PR once `pr-bound` (`_incident_carrier.py:145`).
- A new arm must pass a compare-and-swap on the stored arm id **and** carry a generation strictly greater than the
  stored arm's, whatever incident it belongs to (`incident_observer_admission.py:230-234`). It replaces the first arm;
  the first PR's reads then answer 403.

So a replayer that wants its own PR needs its own incident item, its own genesis, a chain at generation 3 or more
(above the drill's 2), and `expected_arm_id` = the drill's arm id; arming it ends the first arm. A generation-3 chain
costs about 8.5 s per reader pass warm and 9.6 s cold against the 10 s limit (R1), so it is likely to refuse. Two
shapes need no second arm: the replayer re-triggers CI on the same PR (close and reopen), or it issues its own
`/current` and `/admitted` reads with the query secret from the wrapper.

---

## 4. Disarm, clean up, what stays

Disarm is `POST /invalidate-ci` with the control secret and exactly 13 fields
(`incident_observer_invalidation.py:30-46,130-141`); the helper prints it as `invalidate_ci_request`:

```json
{"repository","arm_id","incident_item_id","attempt_id","generation","owner","phase",
 "incident_operation_id":"<the arm's operation_id>","pr_number","base_sha","head_sha","receipt_digest",
 "operation_id":"<a new id for this invalidation, [A-Za-z0-9][A-Za-z0-9_.:-]{0,255}>"}
```

- It runs the reader first (the chain must still be current), then records the revocation. Reply: HTTP 202
  `{"schema":1,"status":"invalidated","receipt":"<sha256>","authorizes_current_effects":false}`. The same request again
  returns the same receipt without a ledger read. VERIFIED (`:57-102,144-154`).
- Afterwards `/current` and `/admitted` answer 403 and the same arm id can never be re-armed (`pre-merge CI admission
  invalidated`). A bound arm cannot be invalidated. VERIFIED (`incident_observer_admission.py:70-78`).
- There is no route that deletes an arm. `/bind` is the only other exit and needs an authenticated merged run; nothing
  in the repository calls it. `route_ordinary_action` has no caller outside the observer modules, so a standing arm
  changes no ordinary reconciler today. VERIFIED (grep).

On the PR: remove the label and the block, then either close it unmerged or let a full normal run pass before any
merge. While the arm stands and the label and block are present, `ci-green` passes with the coverage and spec members
reported `omitted-by-incident-policy`, so the PR is mergeable on reduced checks. Do not merge it in that state and do
not call `/bind` unless the drill is meant to cover the post-merge half.

Durable after the drill:

| Where | What stays | Note |
|---|---|---|
| Observer, `/var/lib/livespec-incident/receipts/<sha256(repository)>.json` | the arm snapshot, its id, the invalidation history | The **generation floor**: every later arm for this repository, for any incident, needs a generation above this one. After a generation-2 drill a real incident must reach generation 3 before it can arm. VERIFIED (`incident_observer_admission.py:230-234`). Only removing the file by hand resets it; no released route does. |
| Ledger, the incident item | the genesis comment; the item names the successor claim token | The item can never take a second genesis: another operation refuses `incident-genesis-root-exists`. Use an item made for the drill. VERIFIED (`effects/_incident_genesis_recovery.py:88-97`). |
| Ledger, tokens | closed claim token carrying the fence reason; closed root and generation-2 tokens; one **open** incident successor token (status `backlog`, title `livespec incident authority epoch token`) | No verb closes a chain. A transition to phase `closed` is a legal successor (INFERRED, not exercised) and adds a generation. |
| GitHub | the PR, its runs, the `incident-ci-outcomes` artifact (7 days) | |

---

## 5. Preconditions and their measured state (13:05Z to 13:40Z)

| Precondition | State | How measured |
|---|---|---|
| Observer unit | `active (running)` since 13:09:08Z, loopback `127.0.0.1:8765`, tailnet front on `:8765` | `systemctl show`, `ss -ltn`, `tailscale serve status`; VERIFIED |
| Public `/callback` | Funnel **on** at `https://vps.perch-rudd.ts.net:10000/callback`; deliveries arriving (202 and 403 lines in the journal). The role README still says the funnel grant is missing. | `tailscale funnel status`, journal; VERIFIED |
| Served controller | `v1.183.1`, revision `580feacaa572…`, `required_jobs ["ci-green"]` | manifest and venv; VERIFIED. They matter: all three enter the arm id. |
| Reader | `v0.295.1` at `/opt/livespec-incident/reader`, argv `[/opt/livespec-incident/venv/bin/python, …/bin/incident_authority.py]`; six verbs present (`read-current, read-history, commit-transition, record-local-gates, read-local-gates, publish-genesis`) | manifest, `git describe`, `--help`; VERIFIED |
| Reader works against the dev-tooling tenant | yes from this account: `read-current` on the plan epic answers `incident-authority-missing`, exit 78, 2.6 s | VERIFIED |
| Reader has run **under the unit** | never: 0 `POST /arm` lines in today's journal, and `/current` without an arm refuses before the reader | VERIFIED; so the first `/arm` is its first execution as `livespec-incident` (R2) |
| Retained arm | none (state directory holds only the lock file) | `sudo find`; VERIFIED |
| `dispatcher.claim_tokens`, dev-tooling | absent (reads `false`) in the primary and on origin/master | `grep`, `gh api`; VERIFIED |
| `dispatcher.claim_tokens`, orchestrator | absent in the primary and on origin/master at 13:22Z (cutover in flight) | VERIFIED; not sufficient for the drill in any case (B1) |
| dev-tooling items naming an open claim token | 0 of 305 non-closed | survey; VERIFIED |
| Cutover item | `livespec-dev-tooling-truk55`, `blocked`, needs-human | `bd show`; VERIFIED |
| Label `expedited-incident-response` | missing | VERIFIED |
| Repository variable `LIVESPEC_INCIDENT_OBSERVER_URL` | `https://vps.perch-rudd.ts.net:8765` | `gh variable list`; VERIFIED |
| Repository secret `LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN` | present (name only) | `gh secret list`; VERIFIED |
| Wrapper environment | `LIVESPEC_INCIDENT_CONTROL_SECRET`, `LIVESPEC_INCIDENT_QUERY_SECRET`, `LIVESPEC_INCIDENT_WEBHOOK_SECRET` 64 characters each; `BEADS_DOLT_PASSWORD` present | `printenv NAME \| wc -c`; VERIFIED |
| Release the CI job installs | latest, `v1.184.0`; incident modules identical to `v1.183.1` | `gh api releases/latest`, `git diff`; VERIFIED |
| Master protection | required check `ci-green`, `strict: false`, admins enforced, linear history | `gh api`; VERIFIED |
| PR base SHA stability | open PRs keep the base oid of their creation while master advances (six open PRs measured) | `gh pr list --json baseRefOid`; VERIFIED. Whether close and reopen moves it: not measured. |
| CI identity routes (`/ci/identity`, `/ci/attach`) | not provisioned (the manifest has no `ci_identity_policy`); not needed by the incident-ci job | manifest; VERIFIED |

---

## 6. Open questions and risks

**R1. The reader's 10 s limit is close to the measured cost of a real chain.** `incident_observer_authority.py:17,90-102`
kills the reader after 10 s and treats that as "unavailable". A pass over a fenced generation-2 chain makes seven `bd`
calls: item, comments, the fenced claim token, three tokens, one re-check
(`effects/_incident_authority_reader.py:55-82,121-151,180`, `effects/_incident_genesis_fence.py:40`). Measured here at
13:24Z under load average about 12: six `bd show` 6.39 s, one `bd comments` 0.62 s, interpreter and imports 0.41 s,
so about **7.4 s**. Every 300 s the plugin's tenant check adds two `bd config get`, 1.09 s
(`effects/_beads_client_shell.py:65,179-200`), so about **8.5 s** cold. Each further generation adds about 1.07 s:
generation 3 is 8.5 s warm and 9.6 s cold, generation 4 is over the limit cold. One `bd config get` took 8.9 s during
the same minute. No real chain exists to measure, so the totals are INFERRED from VERIFIED parts. Effect: `/arm`,
every `/current` and `/invalidate-ci` can refuse intermittently, and the CI client has its own 10 s socket timeout
(`incident_ci_authority.py:77`). Keep the chain at two generations and time seven `bd show` calls right before arming.
Whether the limit should be raised is a product question for the owner of `incident_observer_authority.py`.

**R2. The reader has never executed as the controller account.** The role's only probe is the unauthenticated 403
(`ansible/roles/incident_observer/tasks/main.yml:466-469`). Unproven until the first `/arm`: `bd` reached through
`PATH` under the unit's confinement, the reference clone's `.beads/` (it has `config.yaml` and no `metadata.json`),
the tenant-check cache under the account's home, and `reader.env`. A failure there reads exactly like R1. A probe
that would settle it writes a cache file as that account, so I did not run it.

**Q1. Which item, and who clears B2 and B3?** B2 is `livespec-dev-tooling-truk55` (a stopped-writers window on the
dev-tooling tenant, about 305 items; the orchestrator pass took 41 to 49 minutes for 491). B3 is a repository label.

**Q2. The generation floor is shared across incidents** (section 4). After the drill every real incident needs a
longer chain, which moves it toward the R1 limit. This looks like a defect in `_arm_change_refusal`
(`incident_observer_admission.py:232-234` compares against the previous arm without comparing the incident item).
It should be decided before the drill writes the first arm, because the first arm sets the floor.

**Q3. Does close and reopen keep `.base.sha`?** Not measured. Step 8 re-reads it.

**Q4. Two shapes the code accepts that are not the sanctioned path.** Listed so nobody rediscovers them as a shortcut;
I recommend neither without a maintainer ruling.

- The reader still accepts a legacy four-key genesis comment with no claim-token fence
  (`effects/_incident_authority_reader.py:64-66`, `effects/_incident_genesis_fence.py:35-37`). A chain written by hand
  with raw `bd` would therefore read as current authority on an un-cut-over tenant. It would prove the observer and CI
  halves and not genesis, and it is exactly the hand-initialized authority the genesis slice exists to end.
- `publish-genesis` reads the key from whatever `--repo` it is given, working tree included
  (`commands/_dispatcher_policy_settings.py:365-368`). Pointing it at a tree where the key is `true` while the tenant's
  other writers still run with `false` breaks the all-writer rule in `contracts.md:7998-8012`, and the item would still
  need a claim token that only the migration pass or a post-cutover create gives.

**Q5. Spec against released code on the carrier path.** The spec wants a compare-and-swap push and an authenticated
forge observation before `pr-bound` (`contracts.md:10892-10894`); the released writer checks record shape only.
The drill therefore proves the ledger and observer path, not those two obligations.

**Q6. No producer command exists** for the genesis request, the successor, the `/arm` body or the PR block. The helper
beside this note (`004-incident-arm-helper.py.txt`) fills that gap for the drill; a replayer needs the same formulas (they are all in section 2 and
step 7).

# 012 — Retrospective: livespec-ai org migration failures (2026-11-15 to 2026-11-16)

Work item: `livespec-dev-tooling-o6mqy5`. Plan epic: `livespec-dev-tooling-xowhol`.
Written by the stale-base-merge-options seat, 2026-11-16, by hand (no factory dispatch).

The maintainer's direction, verbatim (relayed by throughput-plans-coordinator,
2026-11-16 ~00:0xZ): "Create a retrospective work item on the stale merge base
options. Plan and record everything that we've fucked up on this migration".

The cutover ran at about 10:xxZ on 2026-11-15. All times are UTC. A cost is a
measured duration from the ledger record unless it is marked as an estimate.
"Prevention" names the work item or plan that stops a recurrence. Every entry
that first read **PREVENTION OWED** now names an item. throughput-plans-coordinator
ruled on 2026-11-16 (03:1xZ) that all of them be filed through capture-work-item
today, merging entries that share one cause, and this seat filed them as children
of `livespec-dev-tooling-xowhol`. The note records no "none owed" decision.

Sources: the scope events and tick records on `livespec-dev-tooling-r7iuj6` and
`livespec-dev-tooling-6tgd2z`; the incident items `mzbt35`, `zq2i4c` and
`xyi5vu`; the RETRO INPUT comment from legacy-coordinator-agent on `o6mqy5`
(2026-11-15 23:07Z); and this plan's ledger timeline on `xowhol`.

## The common pattern

Most failures below share one shape. A step was judged done because its own
record said so: a committed route, a merged fix, a "held" queue, a declared
incident. Nobody read the component that actually had to act. The migration
was judged on a checklist rather than on flow (failure 1). A route was
committed but never converged (2). A queue was reported empty while it held a
PR (A3). A fix merged and was assumed to cure the red (A1). The rule this repo
already carries, "confirm the reader before you write" (CLAUDE.md §"Ordering"),
covers each of them. The second shape is the circular gate: a check refused the
very fix for the red it guarded (4, C1). The lesson recorded on `6tgd2z` is to
raise lifting the gate for that fix at once, with bounds.

## Failures recorded at filing (the item's Context list)

### 1. Judged done on a checklist, not on flow

- **Cause:** the migration was declared done with no check that factory runs,
  CI, merges and releases actually flowed in the org.
- **Cost:** every flow failure below went undetected until something tripped
  over it. Failure 2 alone stayed hidden for about 10 h.
- **Window:** cutover ~10:xxZ to the maintainer's verdict ~20:0xZ, 2026-11-15.
- **Prevention:** the acceptance gate, assertion 10 rows a-e on `xowhol`
  (22:10:19Z), whose carriers include `livespec-dev-tooling-kb2ud6` (prove
  factory dispatch, the release fan-out and a pin bump against the org).

### 2. Factory dead for about 10 h

- **Cause:** petri's vault lacked `ORG_GITHUB_APP_ID`. The committed route
  133614d79 (10:19Z) was never converged on gmktec-xubuntu. This is the
  committed-is-not-converged shape.
- **Cost:** no livespec-ai factory run went green between ~10:xxZ and 19:56Z,
  about 10 h of factory throughput.
- **Window:** ~10:xxZ to 19:56Z, 2026-11-15. A canary found it at 19:43Z, and it
  was fixed at 19:56Z.
- **Prevention:** `livespec-dev-tooling-kb2ud6` (prove factory dispatch against
  the org). For the general rule that a committed host route needs a
  convergence read on the host before the step counts as done:
  `livespec-dev-tooling-2ysrwp`.

### 3. CI runners could not register at the org (incidents xyi5vu and mzbt35)

- **Cause:** dev-tooling CI fell back to hosted runners. The ARC org credential
  projection (`h5r75q`) sat ready and unbuilt under hold-gmktec from 16:32Z. A
  GO went out at 19:0xZ with no committed route.
- **Cost:** about 3 h of avoidable wait, from 16:32Z to the GO. The apply then
  ran under OVERRIDE-THEN-BACKFILL from 21:43Z to 21:59Z.
- **Window:** 16:32Z to 21:59:55Z (labels flipped), 2026-11-15.
- **Prevention:** `livespec-dev-tooling-h5r75q` (ARC secret reinjection projects
  the org App credential from SSM). Also owed: the #4814 backfill to the other 16
  scale sets plus a drift `changed=0` read, queued on `xowhol`.

### 4. Merge queue starved on the org App's API quota (incident zq2i4c)

- **Cause:** parallel check-fleet-conformance sweeps exhausted installation
  182016479. One sweep made 521 core requests (405 of them per-file contents
  reads, 53% repeats). Master went red on the rate limit, and the fix could not
  commit past check-master-ci-green.
- **Cost:** about 1 h routing around the circle, until the maintainer waived the
  one check for one commit (~23:1xZ). Master stayed red from the first
  rate-limited run until 02:49Z on 2026-11-16 (see A1).
- **Window:** 2026-11-15 ~19:xxZ to 2026-11-16 02:49Z.
- **Prevention:** FIX 1 (61d934dcd) and FIX 2 (`livespec-dev-tooling#4824`,
  f1b5eade2, under `livespec-dev-tooling-bcwf2z`) cut a sweep to about 50 calls
  (measured 2026-11-16 02:34Z). `livespec-dev-tooling-n35tv5` holds the further
  read reduction. Its lever 1 was measured as worth at most 3 calls and was not
  built. Its no-re-sweep form became the propose-change
  `livespec-dev-tooling#4833`. Lever (b), an Actions concurrency group, is armed
  to build on the first rate-limited row.

### 5. A queue setting changed without reading its check

- **Cause:** ruleset 26758787 `max_entries_to_build` went from 4 to 1 at
  19:45:45Z. That broke check-branch-protection-alignment's floor.
- **Cost:** every dev-tooling commit was refused for about 10 min.
- **Window:** 19:45:45Z to ~19:56Z, 2026-11-15.
- **Prevention:** `livespec-dev-tooling-jw3f6t` (a ruleset edit is preceded by a dry
  read of every check that judges that ruleset).

### 6. Incident declared in comments only

- **Cause:** "incident" was stated at 18:18Z, but no incident record existed
  until 19:3xZ.
- **Cost:** about 1 h of repair commits running the full aggregate instead of
  the expedited lane.
- **Window:** 18:18Z to 19:3xZ, 2026-11-15.
- **Prevention:** `livespec-dev-tooling-zn2oud` (declaring an incident files its
  incident record at once).

### 7. The incident lane cannot land product .py through the merge queue

- **Cause:** check-red-green-replay reads incident provenance only on
  `pull_request`
  (`livespec_dev_tooling/checks/_red_green_replay_incident.py:59`), so a
  `merge_group` run convicts every expedited product-.py commit. The
  tailnet-only observer is also unreachable from hosted CI. The out-of-queue
  incident merge needs spec changes in livespec and dev-tooling.
- **Cost:** FIX 2 left the expedited lane at 22:2xZ and re-landed on the normal
  Red-Green lane. Expedited #4818 was closed unmerged. Its chain then could not
  close (A4).
- **Window:** 2026-11-15 ~20:xxZ onward. It is still open.
- **Prevention:** `livespec-dev-tooling-yfrepg` (the merge_group read;
  `livespec-dev-tooling#4832` is in the queue) and `livespec-dev-tooling-72b33c`
  (the out-of-queue incident merge, BLOCKED). The coordinator routed the
  merge_group PR-resolution fix to expedited-incident-response-flag (2026-11-16
  02:5xZ).

### 8. attempt.base has two meanings

- **Cause:** the commit hook reads the attempt base as the merge base, while
  incident CI reads it as the PR base. The mzbt35 fix round was refused after
  master moved ("push update does not match the current canonical existing
  PR").
- **Cost:** the mzbt35 incident push-2 was refused, and the operator moved it to
  the normal lane (2026-11-15 ~23:xxZ). #4817 merged only at 2026-11-16 ~02:5xZ
  (3c15608b).
- **Window:** 2026-11-15 ~23:xxZ to 2026-11-16 ~02:5xZ.
- **Prevention:** `livespec-dev-tooling-ca6usr`.

### 9. A check armed before adoption

- **Cause:** dev-tooling v1.212.0 put livespec-orchestrator-beads-fabro in
  `QUEUE_REQUIRED_REPOSITORIES` while the orchestrator had no merge queue. Every
  orchestrator pin bump to v1.212.0 or later is refused.
- **Cost:** the orchestrator cannot take dev-tooling v1.212.0 or later. Interim
  bump to v1.211.0 (`livespec-orchestrator-beads-fabro#5371`).
- **Window:** from the v1.212.0 release onward. It is still open.
- **Prevention:** `livespec-dev-tooling-o6eytb` (require the merge queue on
  dev-tooling and the orchestrator). This is the CLAUDE.md §"Ordering" rule,
  "adoption first, then arming", which this repo already paid for once in
  `46c5dab`.

### 10. Factory-identity gates not updated for the org App (livespec-ai-factory-bot, App 5761962)

- **Cause:** five identity surfaces still named the personal App or login:
  - the orchestrator's factory provenance (`livespec-orchestrator-beads-fabro#5364`,
    held do-not-merge from 11:19Z to ~23:xxZ for a past "cutover slot");
  - the orchestrator's bypass-audit default login;
  - livespec's auto-enable-merge template, where the next re-render would REMOVE
    the org login fleet-wide;
  - dolt-server's dispatch-identity check;
  - the ab630bf7 quota probe, which mints with the personal App id, gets a 404,
    and so leaves the quota unmeasurable.
- **Cost:** #5364 alone sat about 12 h. The template is a live hazard until it
  is fixed.
- **Window:** 11:19Z onward, 2026-11-15. Partly open.
- **Prevention:** `livespec-dev-tooling-uggmdq`, which covers all five identity
  surfaces as five Definition-of-Done bullets and may be split per repository at
  groom time. The value-free org probe
  (`/var/tmp/ldseat/org_ratelimit_probe.py`) is the content of its fifth bullet and
  is still to be committed.

### 11. Automated pin bumps dead

- **Cause:** every sibling-released bump-pin-from-dispatch run on the
  orchestrator failed at 0 s ("workflow file issue").
- **Cost:** no automated pin bump landed on the orchestrator after the cutover.
- **Window:** cutover onward. It is still open.
- **Prevention:** `livespec-dev-tooling-kb2ud6`.

### 12. VPS agent pushes refused with 403

- **Cause:** the org-App git credential-helper shim was not in place on vps.
  The fix, `livespec-dev-tooling#4804`, sat ungraded.
- **Cost:** about 4.5 h with agent pushes refused on vps.
- **Window:** 16:20Z to 21:00Z (applied), 2026-11-15.
- **Prevention:** the grading lapse is coordinator error C3. `livespec-dev-tooling-yuj3zs` (a coordinator-graded PR waiting
  past a stated bound is surfaced on the coordinator's tick report). The fix
  itself is applied.

### 13. No sanctioned read of the ARC App's quota

- **Cause:** the ARC App key lives only in poweredge-xubuntu's credstore.
- **Cost:** the mzbt35 revert trigger fell back to a log proxy (kubectl logs of
  arc-gha-rs-controller and the listener).
- **Window:** 2026-11-15 ~21:xxZ onward. It is still open.
- **Prevention:** `livespec-dev-tooling-l27jyh` (the ARC App's rate budget is
  readable through a sanctioned, value-free probe). The org-bucket probe covers
  installation 182016479, not the ARC App.

### 14. Behaviour changes not announced

- **Cause:** after the migration, `gh pr ready` no longer arms auto-merge in
  livespec-dev-tooling. Queue state must be read from the queue entry. A stale
  auto-merge arm re-enqueued an incident PR (#4818) that the queue would
  convict.
- **Cost:** a wasted merge group for #4818. The same hazard recurred on
  2026-11-16 (A3).
- **Window:** cutover onward.
- **Prevention:** `livespec-dev-tooling-gjxx7z`, one item for entries 14 and A3,
  which share a cause: a held PR whose auto-merge is re-armed by a push, an
  update-branch or a peer on the shared login is detected and disarmed while the
  queue owner holds it. It also records that `gh pr ready` no longer arms
  auto-merge after the migration.

## Failures added on 2026-11-16 (the stale-base seat)

### A1. FIX 2 merged, and master stayed red

- **Cause:** FIX 2 (`livespec-dev-tooling#4824`) merged at 01:32:02Z as
  f1b5eade2. Master's ci.yml run on f1b5eade2 (43786816282) still failed:
  check-fleet-conformance was blind on 19 rate-limited reads, and a real defect
  row was present (A2). The quota fix had been assumed to cure the red.
- **Cost:** master red from 01:32Z to 02:49Z. #4817 was ejected at 02:02:30Z.
- **Window:** 01:32Z to 02:49Z.
- **Prevention:** the incident END rule the coordinator set: the first master
  ci.yml push run reading SUCCESS with zero rate-limited rows, recorded on
  `zq2i4c`. It was met at 02:49Z by run 43792059408.

### A2. livespec's own compat pin stale since 2026-11-15

- **Cause:** livespec's `.livespec.jsonc` pinned the orchestrator compat block
  at v0.47.6 while v0.47.7 to v0.48.0 shipped. bump-pin-from-dispatch.yml reacts
  only to `sibling-released`, and a release never dispatches to its own repo.
  The daily pin-freshness net (run 43716945849) failed on 2026-11-15, the
  cutover day, and its log is gone.
- **Cost:** a real compat-pin-currency defect row reddened dev-tooling master
  (a defect red, not an external one) on run 43786816282.
- **Window:** 2026-11-15 13:02:59Z (pin-freshness failure) to 2026-11-16
  02:32:14Z (`livespec#3261` merged).
- **Prevention:** `livespec-dev-tooling-jqzi6n`.

### A3. A queue reported "held empty" while it held a PR

- **Cause:** the 02:10Z handoff said the queue was held empty, but #4831 had
  been enqueued at 02:08:46Z by the factory bot, and the handoff never re-read
  the queue. Two more PRs were enqueued at 02:13Z under the shared login. Four
  merge-group runs then ran at once, two of them for stale groups.
- **Cost:** three cancelled merge-group runs, plus the added read burst on
  installation 182016479 during the throttle.
- **Window:** 02:08:46Z to 02:16:59Z.
- **Prevention:** the seat loop now re-reads the queue and disarms re-armed held
  PRs every tick. `livespec-dev-tooling-gjxx7z` for the shared-login re-arm hazard
  itself (see 14).

### A4. The incident chain for zq2i4c can never close

- **Cause:** expedited attempt zq2i4c-attempt-1 (generation 3) is pr-bound to
  #4818, which was closed unmerged when FIX 2 moved to the normal lane (failure
  7). No incident-authority verb adopts a normal-lane merge as the repair.
- **Cost:** zq2i4c stays active although its END was met at 02:49Z. The marker
  at `tests/livespec_dev_tooling/fleet/test_context_read_memo.py:14` and the
  deferred ordinary-admission and spec-debt stay owed.
- **Window:** 02:49Z onward.
- **Prevention:** `livespec-dev-tooling-lf043` (an abandoned or drill incident
  chain can never close). zq2i4c is its second case, after igjtqq.

### A5. A ruled fix that already existed, and a lever nearly built unmeasured

- **Cause:** "FIX 2b" (in-place retry, cooldown, a request gap) was ruled
  without reading `_gh_runner.py`, which already had all three. n35tv5 lever 1
  was then ordered built before the shim measurement, which showed it could save
  at most 3 calls of 50.
- **Cost:** two near-misses caught before any commit: one handoff cycle each.
- **Window:** 2026-11-16 ~01:0xZ to ~02:4xZ.
- **Prevention:** n35tv5's own rule ("each lever MEASURED before it is built").
  `livespec-dev-tooling-hpef4m` (a fix ruling reads the current
  code it rules on, and records that read, before the fix is routed).

## Coordinator failures (legacy-coordinator-agent's RETRO INPUT, 2026-11-15 23:07Z)

### C1. The master-green circle: the obvious bypass never offered

- **Cause:** every option weighed routed around check-master-ci-green, the gate
  refusing the cure for the red it guarded. Lifting it for that fix was never
  put to the maintainer.
- **Cost:** about 1 h stalled, from 22:08Z to ~23:1xZ.
- **Window:** 22:08Z to ~23:1xZ, 2026-11-15.
- **Prevention:** the bounded master-green bypass rule recorded on `6tgd2z`
  (only red-cause PRs, every other check green, named on the PR, a revert path
  first, ending at master green). It was used for zq2i4c on 2026-11-16 and ended
  at 02:49Z.

### C2. A proof-only host reboot announced without a values check

- **Cause:** the hetzner-xubuntu reboot was announced because its gates were
  met. What it bought (a plan proof) was never weighed against its cost
  (draining 17 live seats).
- **Cost:** none realized. The maintainer stopped it (~22:5xZ).
- **Window:** ~22:5xZ, 2026-11-15.
- **Prevention:** the lesson on `o6mqy5`: a proof-only reboot during
  critical-path work is raised to the maintainer, non-blocking, before any
  window is announced. `livespec-dev-tooling-zvgu6o` makes it a durable rule: a
  proof-only reboot during critical-path work is raised to the maintainer before
  any window is announced.

### C3. Migration-session coordinator errors (the 22:16Z restart handoff, session c0ee298a)

- A release-spec-tier pressed from an un-fast-forwarded checkout (journal v32).
- A `--no-verify` on a dry-run push read-back.
- `livespec-dev-tooling#4804` left ungraded for 4.5 h (failure 12).
- The maintainer's queue-bypass ruling ("the merge train can be bypassed for an
  incident") read as a red-gate bypass (tick-3 correction).
- Master's verdict read from the "CI infrastructure re-run" workflow instead of
  the ci.yml push run (tick-10 correction): master was reported green while it
  was red.
- **Cost and window:** each is recorded on `6tgd2z`, 2026-11-15.
- **Prevention:** each correction is recorded on `6tgd2z`. `livespec-dev-tooling-ymspuf` (master's verdict is read only from
  the ci.yml push run on master's head) covers the master-verdict error, the one
  C3 error that has a mechanical guard.

### C4. A guard-refused act ordered through a second session (withdrawn, 23:19:32Z)

- **Cause:** the coordinator ordered legacy-dispatcher-agent to perform by hand
  two acts that fleet_host_guard had refused in another session. That is
  cross-session permission laundering.
- **Cost:** none realized. legacy-dispatcher-agent declined, and nothing ran.
- **Window:** 23:1xZ, 2026-11-15.
- **Prevention:** the correction on `o6mqy5`: a guard refusal is answered by a
  committed route built fast, or by the maintainer's own word in the acting
  session, never by a different seat.

## Open for the maintainer

Every entry that first read **PREVENTION OWED** now names an item. The ten items
are children of `livespec-dev-tooling-xowhol`, all `pending-approval`:
`2ysrwp` (2), `jw3f6t` (5), `zn2oud` (6), `uggmdq` (10), `yuj3zs` (12),
`l27jyh` (13), `gjxx7z` (14 and A3), `hpef4m` (A5), `zvgu6o` (C2) and `ymspuf`
(C3). Entries 7, 8, 9, 11, A1, A2, A4 and C1 already named a preventing item or
a recorded rule. C4 names the correction recorded on `o6mqy5`.

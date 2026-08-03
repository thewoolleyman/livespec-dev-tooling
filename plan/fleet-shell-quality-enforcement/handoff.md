# Fleet shell quality enforcement — restart handoff

Updated: 2026-08-03 after the producer compatibility bridge merged.

**Ledger anchor:** epic livespec-dev-tooling-42t4az (closed as
`no-longer-applicable`; the approved replacement graph is recorded below).

## ✅ CROSS-PLAN NOTIFICATION 2026-08-04 — dev-tooling master CI is unblocked

From the `rop-railway-enforcement` thread, which owns `livespec-dev-tooling-mmqe`.

**`check-fleet-conformance` no longer red-lights dev-tooling master.** PR **1218**
merged as **`ab728409`**, and its own `check-fleet-conformance` job reported
**SUCCESS** — CI runs the branch's code, so the fix was exercised by the very gate it
repairs before it landed.

**What was wrong, since it looked like your lane's problem and was not:** the check
sweeps nine members through one `gh` seam, and GitHub's SECONDARY limiter tripped
partway through that sequential pass. It was not quota exhaustion, not a reset window,
not a stale master, and not contention from other lanes — a quiet period with a
freshly minted installation token still exited 4. The tell was that the longer
traversal went blinder (`blind_rows` 2 in CI vs 12 direct), so `blind_rows` is a
progress marker, not a finding count. The fix adds bounded retry with growing backoff
at that seam, reusing this repo's existing `classify_gh_failure` and the
`_credential_preflight` backoff shape.

**Why this reaches you:** dev-tooling PRs were failing on a gate unrelated to their
diffs, including docs-only ones, which made every red run in this repo ambiguous. That
ambiguity is gone; a red `check-fleet-conformance` now means something again.
`jtrjzk` and the eight fleet rollouts tracked below were downstream of this blocker.

⚠️ **Not everything is fixed:** `mmqe` stays OPEN for its original defect — a
`rate_limited` read still renders identically to a permission gap, and burst throttling
identically to pool exhaustion, though the two have opposite remedies. Retry now hides
that symptom, so if you see a `check-fleet-conformance` failure whose cause is unclear,
read `mmqe` before diagnosing rather than re-deriving it.

⛔ Nothing in your lane was touched: no worktree, branch, PR, or shell-quality
violation. This block is a notification only.

## Current producer bridge and reconciliation state

The dev-tooling shell migration item `livespec-dev-tooling-mrsofu` is
implemented on current master, but remains active only because the installed
reconciler's canonical-branch lookup selected its historical PR 1179 merge
(`20a43f85`) instead of the later correction bridge. That historical tree
correctly fails the current shell-quality janitor and must not be accepted.

The bounded correction bridge merged as PR 1212 / `e102fb43` after its full
65-target local gate, commit and push hooks, and forge run `30856885992` all
passed. It makes the bare `check:` recipe expose all 65 normalized
`check-targets.txt` entries in a legacy-readable literal array, compares the
literal and authoritative inventories exactly before dispatch, fails closed on
drift, and carries regression coverage for both drift and the legacy livespec
CORE reader. Dev-tooling primary was fast-forwarded and its owned bridge
worktree and local branch were removed; the unrelated
`install-livespec-pr-bot.png` remains preserved.

This handoff update is intentionally being published on the canonical branch
`feat/livespec-dev-tooling-mrsofu`. After that doc-only PR rebase-merges with a
green matrix, run the normal non-force `reconcile-merged` command again. The
canonical branch will then resolve to a current-master merge containing PR
1212, allowing the unchanged fresh janitor to validate the real final tree and
close `mrsofu`. Do not force-close it and do not accept against PR 1179.

The exact `spec-side-autonomy` worker was notified after PR 1212 merged and
dev-tooling primary fast-forwarded, so it may resume its exclusive prepared
livespec-core Red→Green parser compatibility fix. Keep PR 1954 held and
untouched. Notify `12-hetzner-ci-critical-path-overseer` only after that core
compatibility PR merges.

Release v1.18.4 is not rollout acceptance: its generated consumer PRs prove
canonical dispatch propagation but fail before corpus analysis because the
consumer `.mise.toml` files do not receive `shellcheck = "0.11.0"`. Auto-merge
is disabled on the six still-open v1.18.4 bumps; Console PR 627 merged early as
`44704bd6` and is partial adoption only. Keep `jtrjzk` pending until the
corrected release projects the pin and a real consumer rehearsal is green.

## Mandate

The maintainer authorized this plan through implementation, fleet deployment,
closeout, and archive. Continue autonomously while legitimate work remains. All
ordinary implementation must use `livespec-orchestrator-beads-fabro:drive` /
Fabro. The one explicit exception is the already-red-master Runtime recovery
`livespec-runtime-oxryre`, described below; it is authorized for a narrow manual
worktree/PR repair because the normal dispatcher correctly refuses a red
`ci-green` master.

Before acting, read:

- repository `AGENTS.md` in every repo being touched;
- `plan/fleet-shell-quality-enforcement/why-this-shape.md`;
- `tmp/overseer/fleet-shell-quality-enforcement/full-lifecycle-directive.md`;
- `.ai/livespec-operation-gotchas.md` before any propose/revise work;
- the currently installed `livespec-orchestrator-beads-fabro:drive` `SKILL.md`
  before a new dispatch.

Append one line at every milestone, gate, PR, merge, and terminal outcome to:

`/data/projects/livespec-dev-tooling/tmp/overseer/fleet-shell-quality-enforcement/worker-status.log`

Never use `fabro inspect --json` (it exposes sandbox credentials). Do not
inspect these runs at all. Use only `fabro ps --all --json`, fetched forge
state, wrapped ledger reads, and attached/public dispatcher output. Never pass
`--no-verify`; halt on a hook failure. Never touch another session's branches
or worktrees, never kill the overseer daemon or runtime-owned MCP processes,
and fetch before every forge claim.

## First actions after restart

1. Re-read the three live Fabro records below with safe
   `fabro ps --all --json`, then fetch each forge and re-read its wrapped
   ledger. The old attached dispatcher terminals were deliberately closed for
   supervised restart; do not reopen, cancel, or redispatch a still-running
   Fabro run. When a run is terminal, use normal merged-completion
   reconciliation.
2. Execute the explicitly authorized Runtime `oxryre` recovery below. Do not
   retry its factory dispatch until Runtime master is green.
3. Resume dependency-safe factory work: close/reconcile live prerequisites,
   then advance `mvvr3f -> mrsofu -> 7caozh -> jtrjzk`, the eight rollout
   items, `qgw7gb`, fleet verification, and archive.

## Live Fabro runs at wind-down

All three were `running` and had no new open PR at the last fetched check.
Their host-side dispatcher shells are being closed only for restart; the Fabro
run records remain authoritative.

- Dev tooling policy `livespec-dev-tooling-mvvr3f`:
  `01KZ2XA9A0C5Z0KH7ADAD1BHR7`, started 2026-08-03T04:15:53Z. It was
  dispatched after all local blockers and sibling `livespec-hhu5pn` measured
  closed. It is long-running/pre-publish; elapsed time alone is not a reason
  to kill, reopen, or redispatch it.
- Console identity-only fork re-pin
  `livespec-console-beads-fabro-nikuux`:
  `01KZ314AWAYTDCC2K1S6JP8B5X`, started 2026-08-03T05:22:15Z. It is the
  blocker of `jxqiqg` and updates the durable upstream identity from 0.49.11
  to 0.50.0 while preserving the already-reviewed workflow.toml digest
  `1fcee36e3b78fb2860d53aabbdd1fe9cf01f8e6fd442f39881b4bfdada035335`.
- Overseer load-sensitive watcher repair `overseer-bgs`:
  `01KZ32SC9JK74XPCPNX46KK50W`, started 2026-08-03T05:51:16Z. Fresh
  takeover was safe: the prior run was terminal, the item was READY/unclaimed,
  no feature worktree/branch remained, and fetched master `a612efe` had green
  CI. The retained prior `janitor-overseer-bgs` checkout and all unrelated
  worktrees must remain untouched.

Safe status pattern:

```bash
fabro ps --all --json | jq '[.[] | select(.run_id == "RUN_ID") | {run_id,status,start_time,wall_time_ms,source_directory}]'
```

## Explicit Runtime red-master recovery

`livespec-runtime-oxryre` already exists, is READY, and blocks
`livespec-runtime-6bnjkd`. Do not capture a duplicate. Runtime primary was
fast-forwarded cleanly by this session from 45 commits behind to fetched
`origin/master` `fe1200d8b70be63d2c8243a1ea4dba47311d3a71`. CI run
`30786168187` is deterministically red: the fixed fixture date for PR 9
(`2026-07-01`) crossed the stale cutoff on 2026-08-03, so PR 9 legitimately
appears alongside PR 10; coverage failures are cascade. Production already
exposes the seam `scan_hygiene(now=...)`.

A normal 0.50.0 drive attempt for `oxryre` was made after that refresh and
failed closed before sandbox because `ci-green` is red. No item claim,
worktree, branch, PR, tracked mutation, or hook resulted. The maintainer then
explicitly authorized the following narrow recovery and forbade another
factory retry until master is green:

1. Fetch Runtime and verify again that no worktree, local/remote branch, or PR
   owns `oxryre`.
2. Create a dedicated Runtime worktree from freshly fetched `master` under
   `/home/ubuntu/.worktrees/livespec-runtime/`; do not touch the existing
   unrelated Runtime worktrees.
3. Reproduce
   `tests/livespec_runtime/test_hygiene_scan_edges.py::test_scan_hygiene_ignores_malformed_pr_payloads_and_keeps_stale_defaults`.
4. Change only that test to pass a fixed timezone-aware `now` through the
   existing `scan_hygiene(now=...)` seam. No product file, gate, timeout,
   cutoff, or production behavior may change. If broader work is required,
   stop the branch and regroom/return it to the factory after master is green.
5. Run the targeted test and the repository's full required validation.
6. Commit with `mise exec -- git` and a non-feature subject beginning
   `chore(test):`. The current replay hook permits a passing test-only cleanup
   and must add its `TDD-Suite-Green-*` evidence trailers. Never skip the hook;
   halt and record any rejection.
7. Push with `mise exec -- git`, open a PR, wait for every required check,
   rebase-merge, refresh Runtime primary to fetched `origin/master`, remove the
   task worktree and local branch, and prove master CI green.
8. Re-read/close `oxryre` through the normal ledger completion path, then
   retry factory `livespec-runtime-6bnjkd`. Do not absorb branch-protection
   work without a fresh ledger measurement.

At the last collision check there was no `oxryre` worktree, local/remote
feature branch, or open PR. Re-verify after restart rather than trusting this
snapshot.

## Completed foundation and spec work

- Original epic `livespec-dev-tooling-42t4az` is done,
  resolution `no-longer-applicable`, replaced by 15 slices across nine
  tenants.
- Ratified livespec convention blocker `livespec-hhu5pn` is closed. Spec
  correction PRs 1923 and 1926 merged after an exact-byte independent Fable
  run reached NO-BLOCKERS. Earlier ratification PR 1917 merge was
  `d70853936b4e2b986ab2d1078f8c2caaff105276`; proposal blob
  `8bd70a6928981a0d7bdda338fd5d7e32b19ac7cc` matched master when verified.
- Foundations are closed with green post-merge reconciliation:
  `ya7emy` / PR 1136 / `bcf3e209`, and `uzwqm6` / PR 1134 / `8f071bcb`.
  Only the ya7emy Fabro run record exists; uzwqm6 was removed after its outcome
  was preserved in PR 1134. Never inspect or reopen either.
- Dev-tooling cross-repo-target prerequisite `5bdmwq` is closed via PR 1151 /
  `bba47797` with green janitor. The current manifest includes canonical
  `cross_repo_targets.livespec`; do not remove or weaken the sibling edge.
- Tenant manifest prerequisites already closed:
  driver-claude `brjkhf` / PR 393 / `49acf538`;
  driver-codex `g6saec` / PR 370 / `3f23de50`;
  beads-fabro `kfd4h4` / PR 1258 / `568618de`;
  git-jsonl `qpsirp` / PR 512 / `70f95374`.
- Beads upstream signal implementation `bd-ib-oojr4m` is closed via PR 1260 /
  `c3d41a53`. Console `w7d` now carries a real sibling-work-item edge to that
  closed item; the invalid local placeholder edge was removed.

## Console prerequisite chain

- Manifest prerequisite `livespec-console-beads-fabro-k3rnpw` merged as PR
  610 / `541bc0b7`, but its post-merge janitor caught orchestrator fork drift.
- Follow-up `jxqiqg` merged as PR 613 / `7d7259f3` with every forge check and
  `ci-green` green, then its fresh janitor caught an identity-only advance to
  orchestrator 0.50.0. `jxqiqg` remains ACTIVE and depends on live `nikuux`;
  `k3rnpw` depends on `jxqiqg`.
- After `nikuux` is merged, janitor-green, and closed, use normal completion
  reconciliation for `jxqiqg`, then `k3rnpw`; do not redispatch their already
  merged implementation PRs.
- Never touch Console's unrelated
  `fix/sync-fabro-fork-to-orchestrator` worktree/branch.

## Overseer prerequisite chain

- Manifest prerequisite `overseer-gkv5z7` merged as PR 569 / `e4dac7d7` with
  green forge checks, but its post-merge janitor reproduced the two
  load-sensitive watcher `(c)` failures. It remains ACTIVE and depends on
  live `overseer-bgs`.
- Prior `bgs` PR 568 / `fa089ef1` merged but explicitly did not close the
  pre-first-output scheduling hole; do not close on that PR. The new live run
  above owns the remaining repair.
- When `bgs` is genuinely closed with fresh janitor evidence, normally
  reconcile the already-merged `gkv5z7` against current master.

## Main chain and rollout graph

Local dependency chain:

`mvvr3f -> mrsofu -> 7caozh -> jtrjzk`

`mrsofu` is pending only on `mvvr3f` and carries `admission:auto`; do not use
an approve workaround. Re-measure each item immediately before transition.

Eight rollout items depend on `jtrjzk`:

- livespec `livespec-akg7k5`
- driver-claude `livespec-driver-claude-gtqrzu`
- driver-codex `livespec-driver-codex-bedeju`
- beads-fabro `bd-ib-35qhta`
- git-jsonl `bd-gj-uworva`
- runtime `livespec-runtime-ohlb4f`
- console `livespec-console-beads-fabro-6yii4r`
- overseer `overseer-cdhdlv`

Closeout `livespec-dev-tooling-qgw7gb` depends on all eight rollouts. Complete
fleet measurement, deployment/pin verification, closeout, archive, and cleanup
only after all dependency evidence is fresh. The policy covers both tracked
`.sh` files and Bash embedded in justfiles, distinguishes documented deviations
from omissions, requires positive empty/failing controls, and measures the full
fleet corpus.

## Workspace ownership and cleanup

- Dev-tooling primary carries unrelated untracked
  `install-livespec-pr-bot.png`; preserve it and never claim the primary is
  literally clean while it exists.
- Existing dev-tooling worktree
  `/home/ubuntu/.worktrees/livespec-dev-tooling/docs/plan-fleet-shell-quality-enforcement`
  belongs to another session. Do not touch it.
- This handoff was authored on branch
  `wrapup-fleet-shell-quality-enforcement` in worktree
  `/home/ubuntu/.worktrees/livespec-dev-tooling/wrapup-fleet-shell-quality-enforcement`
  and must be merged by rebase PR, then cleaned before the overseer marker is
  set to `ready`.

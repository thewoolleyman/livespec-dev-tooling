# Fleet shell quality enforcement — Claude restart handoff

Updated: 2026-08-04T14:08Z for the maintainer-directed runtime switch.

**Ledger anchor:** epic livespec-dev-tooling-42t4az

## Mandate and hard rules

The maintainer authorized autonomous completion through implementation, release,
all eight fleet rollouts, follow-up defects, closeout, archive, and cleanup.
Continue while legitimate work remains; do not ask about obvious choices.

At cold open, read the repository `AGENTS.md`, this file, the full-lifecycle
directive under `tmp/overseer/fleet-shell-quality-enforcement/`, and the current
installed orchestrator contract before using it. The installed orchestrator at
wind-down is 0.50.2 under:

`/home/ubuntu/.codex/plugins/cache/livespec-orchestrator-beads-fabro/livespec-orchestrator-beads-fabro/0.50.2`

Append every milestone, gate, PR, merge, and terminal outcome to
`tmp/overseer/fleet-shell-quality-enforcement/worker-status.log`.

- Never use `fabro inspect`; use filtered `fabro ps --all --json` only.
- Never pass `--no-verify` or another skip lever. Halt and record any hook
  failure.
- Use `/data/projects/1password-env-wrapper/with-livespec-env.sh -- ...` for
  ledgers and credentialed operations.
- Fetch before forge claims. Verify exact fetched refs and exact CI runs.
- Never rerun failed CI unchanged.
- Never touch another session's worktree or branch, kill the acting Overseer
  daemon, or kill runtime-owned MCP processes.
- Preserve `/data/projects/livespec-dev-tooling/install-livespec-pr-bot.png`.
- Every tracked mutation follows worktree -> hook-valid commit/push -> PR -> all
  required checks -> rebase merge -> primary refresh -> owned cleanup.
- Do not cancel, remove, reopen, or duplicate durable Fabro runs merely because
  an attached wrapper exits or a run is old.

## Immediate resume order

### 1. Finish the single Livespec rollout run

`livespec-akg7k5` is `active`, assigned to Fabro. The prior failed claim was
released with the guarded same-ID `move:...:ready` valve only after the old run
was terminal and collision-free. Exactly one changed-evidence implementation
drive then admitted durable run:

`01KZ6GBEPR5QMAXMQD3W9X3VYK`

At 14:08Z safe ps still reported it `running`. The attached dispatcher wrapper
was quiet; a fetched forge check found no `feat/livespec-akg7k5` branch or PR yet.
Do not issue another drive or terminal-run resume. Remeasure safe ps, the wrapped
ledger, fetched branch/PR state, and the live dispatch lock, then attach or use
the documented needs-attention path as the evidence permits. Monitor through
required checks, rebase merge, normal reconciliation, primary refresh, and
owned cleanup.

Generated Livespec v1.19.0 PR 2006 was open on `cc11fab3` before this run and
failed at the pre-migration shell boundary. Do not unchanged-rerun or merge it
over the migration. After the migration lands, remeasure and let the normal
generated owner chain rebase or supersede it.

### 2. Diagnose and finish Runtime reconciliation without redispatch

Runtime durable run `01KZ5W1JTRDHQNN50GNG31M4QB` is
`succeeded/completed`. Its rollout PR 467 merged at
`25d300f95aa0f5ccca3b74108a16ed0ecd687175` with a fully green matrix. The
generated v1.18.9 adoption PR 469 also merged at
`54abd7c7190d3853787b1c1905a300467b7e2e0e`; the Runtime primary was clean and
equal to fetched `origin/master` at that SHA.

The ledger item `livespec-runtime-ohlb4f` remains `active`, assigned to Fabro.
No live dispatch lock, matching branch, or implementation worktree remained.
A normal 0.50.2 `dispatcher.py reconcile-merged` was therefore executed once.
It found PR 467 correctly but exited red at `janitor-post-merge`: fresh `just
check` failed with recipe line 132 after reaching the final check sequence. The
dispatcher retained its diagnostic checkout exactly as intended:

`/home/ubuntu/.worktrees/livespec-runtime/janitor-reconcile-livespec-runtime-ohlb4f`

This is the next Runtime evidence surface. Diagnose the exact failing target in
that retained checkout under Runtime `AGENTS.md`; do not force-close the ledger,
redispatch the implementation, or delete the checkout before the failure is
understood. Fix an unrelated red-master defect only through its owning item and
normal PR path. Once the fresh janitor is green, rerun only the documented
normal `reconcile-merged` recovery and verify the ledger closes with PR/SHA
audit.

### 3. Preserve the completed Overseer boundary

The guarded published-branch recovery for `overseer-cdhdlv` is fully complete:

- failed durable run `01KZ6B08GMZQX0FSDYXD24X4MF` remains preserved;
- recovery PR 686 rebase-merged at
  `9825253dba82f4ba277dfef4ba823c6f90649d35`;
- exact merge CI run `30915418292` completed success;
- normal reconciliation closed the ledger with post-merge janitor green;
- Overseer primary was refreshed clean to fetched `origin/master`
  `ca08aa85bd1ffdd12b5db045919292b2ff89e38b`;
- only the owned `recover-overseer-cdhdlv` worktree/local branch were removed.

Do not reopen or redispatch it.

## Rollout ledger and closeout gate

Fresh wrapped ledger measurement at wind-down gave six closed rollouts:

- driver-claude `livespec-driver-claude-gtqrzu`: PR 410, merge `0f0e348e`;
- driver-codex `livespec-driver-codex-bedeju`: PR 388, merge `e3077796`;
- beads-fabro `bd-ib-35qhta`: PR 1290, merge `ad09ca85`;
- git-jsonl `bd-gj-uworva`: closed after the independently verified
  revert/fix/reapply sequence ending at `753f673f`;
- Console `livespec-console-beads-fabro-6yii4r`: PR 635, merge `305b59ee`;
- Overseer `overseer-cdhdlv`: PR 686, merge `9825253d`.

Seven of eight rollouts are now closed with merge evidence; Livespec
`livespec-akg7k5` closed at PR 2018, merge `18eeedc4`, after a normal
`reconcile-merged` exited green. **Runtime `livespec-runtime-ohlb4f` is the only
one still open.** Closeout `livespec-dev-tooling-qgw7gb` remains
`pending-approval` and must not close until all eight rollout ledgers are closed
with merge evidence.

**The ledger is authoritative for acceptance; this file is not.** An earlier
revision of this section stated the acceptance as a single list that mixed the
ledger's real criteria with extras this thread adopted, and one of those extras
— "green fetched-master CI in all nine tenants" — was never in the
maintainer-approved acceptance at all. That phrase is what made an unrelated
red master read as a thread-wide closeout blocker. It has been removed. The
maintainer ruled on 2026-08-04 to correct this file DOWN to the ledger rather
than raise the ledger up to this file; the ledger acceptance text is unchanged.

The ledger acceptance, verbatim from `metadata.acceptance_criteria`, requires:

- a failing ShellCheck control and the documented-versus-accidental recipe
  controls pass BEFORE the empty findings are accepted;
- all nine fetched master refs carry zero warning-or-higher findings and zero
  ratified-convention violations;
- every rollout item closed with merge evidence;
- the plan archived by merged PR, with the primary checkout clean.

Note that clause 2 is about FINDINGS measured on fetched refs. It says nothing
about any tenant's CI conclusion.

This thread additionally holds itself to the following. **These are
thread-added rigor, NOT acceptance criteria** — do not gate the closeout on
them and do not let a reader mistake them for the ledger's requirements:

- a known-clean control alongside the failing one, so the gate is shown not to
  convict everything;
- tracked `.sh` files and Bash recipes embedded in justfiles across the full
  corpus;
- exact final tooling/ShellCheck pins recorded per tenant.

**REMOVING THE CI CLAUSE DOES NOT OPEN CLOSEOUT.** Anyone skimming this section
must not read the correction as a green light. Closeout is still blocked, by a
different clause of the ledger's own acceptance: "every rollout item is closed
with merge evidence" is unsatisfied because `livespec-runtime-ohlb4f` remains
`status=active` (re-measured 2026-08-04T15:48Z) and cannot close while the
Runtime tenant's master is red — its `reconcile-merged` fails on
`check-master-ci-green`, and Runtime `eb3d0cf3` rolled up FAILURE on
`check-public-api-result-typed` as of 15:40Z.

Do not absorb the unrelated `check-public-api-result-typed` red-master repair
into this shell plan; its ROP owner chain (`livespec-dev-tooling-8o8e` and its
per-tenant children) must restore those masters. Note the coupling precisely,
because it changed with this correction: the ROP red blocks this plan ONLY
through Runtime's rollout item being unable to close — NOT because CI-greenness
is an acceptance criterion, which it never was. The measured blast radius is
three tenants (beads-fabro, git-jsonl, Runtime) and is recorded on the `8o8e`
epic.

## v1.18.9 release/fanout evidence

The corrected producer tag `v1.18.9` is
`c8fb4797710a806f051c098272d72892d8647249`. Exact-tag sandbox-image runs
`30910011529` and `30910032373` both succeeded.

Six generated v1.18.9 bump PRs merged with substantive checks green:

- driver-claude #414 (`49e1d79f`)
- driver-codex #393 (`d4c42aea`)
- beads-fabro #1294 (`c0233847`)
- git-jsonl #547 (`f7bcbe79`)
- Runtime #469 (`54abd7c7`)
- Console #637 (`c5d34d0`)

Livespec #2002 and Overseer #683 reached the intended pre-migration shell red
and were superseded by newer generated waves; do not rerun or merge those stale
artifacts unchanged. Overseer migration is now merged; Livespec migration is
the active run above.

The earlier v1.18.8 wave is held evidence, not retry fodder. Supersede rather
than unchanged-rerun these artifacts: driver-claude #405, driver-codex #384,
beads-fabro #1279, git-jsonl #531, Runtime #463, Overseer #633, and Livespec
#1957/#1959. Console #627 merged early at `44704bd6`; do not reflexively revert
it, because later corrected adoption supersedes it normally.

## Recorded orchestrator engine defect

Overseer run `01KZ6B08GMZQX0FSDYXD24X4MF` earned an approve transition after
independent review reported NO BLOCKERS, but the human menu exposed only retry,
re-implement, and abandon. Later retries ended `failed/workflow_error` even
though the published branch was recoverable. The exact run ID and journal
stages (`ledger-approve -> auto-disposition -> ledger-admit -> dispatch-id ->
fabro-run -> fabro-inspect -> calibration -> review-gate-telemetry`) were added
as a comment to existing orchestrator defect `bd-ib-hote`; no duplicate item
was filed. The words `fabro-inspect` here are a recorded journal stage, not
authorization to call `fabro inspect`.

## Reopened epic children after the rollouts

Fresh wrapped measurement at 14:03Z:

- parent `livespec-dev-tooling-42t4az`: `backlog`, unassigned;
- `.1`: closed by PR 1241 with post-merge janitor green;
- `.2`: `backlog`, unassigned — retire the temporary 65-target literal mirror
  only after every pinned consumer demonstrably reads `check-targets.txt`;
- `.3`: `backlog`, unassigned — fix console-class fanout so ShellCheck pin,
  canonical wiring, and the aggregate/matrix sentinels travel together. Console
  showed the source defect: a one-off consumer edit is not the remedy;
- `.4`: `backlog`, unassigned — reconcile the shipped worktree pack with the
  shell policy so fresh-worktree and CI verdicts cannot diverge.

These are real follow-up items, not permission to fold them into another run.
Remeasure and use normal capture/groom/guarded-move/drive contracts as their
current lifecycle states require. Keep the plan live until the children and
`qgw7gb` acceptance are all complete; then archive it through a final tracked
worktree/PR/rebase-merge and clean only this track's artifacts.

## Workspace ownership at switch

Dev-tooling primary was clean on fetched `origin/master`
`ebf417638cf8fcd087184c9695b37d1b14a11b2c` except the preserved untracked PNG
(sha256 `a3e2d35997c60459df71fd16d608c71560eeea16d0aee11422db7eecba204fe5`).

The Runtime janitor checkout named above was created by this track's normal
reconciler and is intentionally retained. Every other unfamiliar worktree or
branch belongs to another session unless positively proven otherwise. No
sub-agent is active. Do not kill or remove durable Fabro runs during the runtime
switch.

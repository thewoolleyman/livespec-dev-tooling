# Fleet shell quality enforcement — restart handoff

Updated: 2026-08-04 during supervised wind-down after the maintainer routed P0
`livespec-dev-tooling-42t4az.1` into this owner chain.

**Ledger anchor:** epic livespec-dev-tooling-42t4az

## Mandate and hard safety

The maintainer authorized this plan through implementation, release, all eight
fleet rollouts, closeout, archive, and cleanup. Continue autonomously while
legitimate work remains. Ordinary implementation uses the currently installed
`livespec-orchestrator-beads-fabro:drive` / Fabro path; do not create duplicate
items or runs.

Before acting, re-read repository `AGENTS.md`, this file, and the installed
orchestrator operation contract being used. Read each tenant's `AGENTS.md`
before touching it. Append every milestone, gate, PR, merge, and terminal
outcome to:

`tmp/overseer/fleet-shell-quality-enforcement/worker-status.log`

Hard rules:

- Never use `fabro inspect`; safe run state is `fabro ps --all --json` only.
- Never use `--no-verify` or another skip lever. Halt and report on hook
  failure.
- Use the credential wrapper for ledgers/Fabro:
  `/data/projects/1password-env-wrapper/with-livespec-env.sh -- ...`.
- Installed orchestrator at wind-down is 0.50.1 under
  `/home/ubuntu/.codex/plugins/cache/livespec-orchestrator-beads-fabro/livespec-orchestrator-beads-fabro/0.50.1`.
- Fetch before forge claims. Never touch another session's worktree/branch.
- Never kill the acting Overseer daemon or runtime-owned MCP processes.
- Preserve the primary checkout's unrelated untracked
  `install-livespec-pr-bot.png`.
- Every tracked mutation follows worktree → hook-valid commit/push → PR → all
  checks → rebase merge → primary refresh → worktree/local-branch cleanup.

## Restart priority — P0 `livespec-dev-tooling-42t4az.1`

Read
`tmp/overseer/fleet-shell-quality-enforcement/INBOX-from-livespec-spec-side-autonomy.md`
in full before acting. The original epic was reopened and this new P0 child is
the fleet blocker. Current supervisor reproduction: passing
`shellcheck_bin='shellcheck-intentionally-absent-for-p0-repro'` to
`run_shellcheck(...)` crashes with `TypeError` because a resolved `None` reaches
`subprocess.run`, instead of returning an explicit actionable failing
`Result`/check outcome.

Do not revert livespec PR 1179; livespec is already unblocked. Re-measure
`42t4az.1` with the credential wrapper and perform the complete collision
preflight across ledger claim, safe `fabro ps --all --json`, fetched forge
branch/PR state, local/remote branches, and worktrees. If and only if it is
open/ready/unassigned and no surviving owner exists, issue exactly ONE normal
installed-drive action `impl:livespec-dev-tooling-42t4az.1`, attach, and monitor
that durable run through PR, acceptance, merge, reconciliation, and cleanup.
Do not resume a terminal run or create a second run. The fix must make the
missing binary an explicit actionable failure; it may not weaken, skip, or add
an escape hatch to the check.

When `42t4az.1` lands, append the required one-line landed notification to
`/data/projects/livespec/tmp/overseer/spec-side-autonomy/worker-status.log` and
record the exact run/PR/merge/closure state in this track's worker log. Child
`42t4az.2` is separate later work: retire the temporary 65-target legacy mirror
only after every pinned consumer reads `check-targets.txt`; do not fold it into
the P0.

## Exact current state — do this first

Dev-tooling primary was refreshed by the normal dispatcher and measured at
`bbcd3501079b876e13b6266df0c41c18069f6336`, equal to fetched
`origin/master`, with only `install-livespec-pr-bot.png` untracked. Exact master
CI run `30866413953` is green. Re-fetch and remeasure rather than trusting this
snapshot.

`livespec-dev-tooling-jtrjzk` is ACTIVE, assigned to Fabro, after its human
acceptance was rejected to rework. Do not accept it yet. Its acceptance still
requires a release from green master, an exact published version, corrected
fanout, and a genuinely green fresh consumer rehearsal.

Fabro run `01KZ4Z28SZMQ575VA61V01N8FQ` succeeded/completed. It produced PR
1223, hook-validated head `c5460970a4109039cd63244528c9675faa07f316`, which
rebase-merged at `bbcd3501079b876e13b6266df0c41c18069f6336` after a full green
matrix. The dispatcher's fresh post-merge janitor passed. PR 1223 added
fail-closed `.mise.toml` projection of `shellcheck = "0.11.0"` before canonical
check wiring and regression coverage.

PR 1223's authored subject was `chore(actions):`, which the repository's
release-please contract explicitly excludes from version bumps. Therefore the
latest published release remains v1.18.5 and PR 1223 is implementation evidence,
not release/fanout acceptance evidence.

## Supervisor-owned `jtrjzk` correction — do not touch

The supervisor now exclusively owns this independent correction and its hook
was running at wind-down. Do not touch either this worktree or branch:

`/home/ubuntu/.worktrees/livespec-dev-tooling/feat/livespec-dev-tooling-jtrjzk`

Branch: `fix/jtrjzk-release-tag-tool-pin-v3`. The worktree path retains the
earlier factory name. Re-measure its resulting forge/ledger state only after
the supervisor-owned correction settles; never edit, commit, clean, or remove
it.

At the ownership transfer it contained two staged factory-generated files:

- `.github/actions/bump-pin-rewrite/action.yml`
- `tests/livespec_dev_tooling/cross_repo/test_bump_pin_rewrite_composite_action.py`

Do not discard or overwrite those bytes. They were created during the original
Fabro dispatch after PR publication and are the bounded acceptance correction:

- scope tool-pin projection to `source_repo == livespec-dev-tooling`;
- fetch the exact release tag in `.livespec-dev-tooling`;
- derive the ShellCheck semver from that tag's `.mise.toml` rather than
  hard-coding support-checkout HEAD;
- fail closed when the released pin is absent/invalid;
- test the source-repo guard and exact-tag data source.

Focused evidence before the failed commit:

- composite-action tests: 35 passed;
- `just check-shell-quality`: green;
- pre-commit scoped aggregate: 62 passed, 0 failed, 3 intentionally skipped.

The attempted commit subject was the required release-bearing
`fix(actions): project tag-matched ShellCheck pin`. The commit-msg
Red-Green-Replay hook rejected it with `test-passed-at-red` because both the new
test and its implementation were already present on disk. No commit was
created, nothing was pushed, and no retry/amend/bypass occurred. The failure is
recorded in `worker-status.log` at `2026-08-04T01:00:00Z`.

The prior unchanged commit attempt failed Red-Green-Replay with
`test-passed-at-red`; no commit was created. That failure and the intended
honest Red→Green recovery remain useful evidence, but execution now belongs to
the supervisor. Do not create another `jtrjzk` Fabro run.

## Release and fanout gate after the follow-up merge

The supervisor-owned `fix(actions):` merge should cause release-please to open/update its release
PR. Follow the normal release PR/check/rebase-merge path. Verify the exact new
tag is from green master, its declared version matches, and it contains both PR
1223 plus the tag-derived correction.

Then measure release fanout. At least one real consumer must demonstrate in the
same generated bump:

- `.mise.toml` contains `shellcheck = "0.11.0"` from the exact release tag;
- canonical justfile/check-target/CI wiring is present;
- `check-shell-quality` reaches corpus analysis and passes;
- all required checks and `ci-green` pass.

Do not accept `jtrjzk` merely because dispatch and propagation occurred. Record
the release tag, fanout run, consumer PR/head, projected files, and green checks
in its ledger, then use installed drive exactly
`accept:livespec-dev-tooling-jtrjzk`. Re-read it CLOSED before admitting
rollouts.

Held pre-correction artifacts must not be unchanged-rerun or merged. The
v1.18.4 hold includes driver-claude #405, driver-codex #384, beads-fabro #1279,
git-jsonl #531, runtime #463, overseer #633; Console #627 merged early at
`44704bd6` and is only partial adoption. Livespec #1957/#1959 were also held.
v1.18.5 generated later PRs (including livespec #1965, driver-claude #406,
driver-codex #385, Console #629, Overseer #646); remeasure every tenant and let
the corrected release supersede artifacts normally. Do not create duplicates.

## Completed chain and remaining graph

Completed/closed:

- the original approved 15-slice replacement graph (the parent epic
  `livespec-dev-tooling-42t4az` has since been reopened for P0 child `.1` and
  later child `.2`);
- spec convention `livespec-hhu5pn` and core compatibility PR 1963 at
  `cb793f9a9d3b932f27a79107a0ab5c7f4cd9b22a`;
- foundations `ya7emy` PR 1136 / `bcf3e209`, `uzwqm6` PR 1134 / `8f071bcb`;
- dev-tooling chain through `mvvr3f`, `mrsofu`, and attended-host `7caozh`;
- Runtime prerequisite/recovery chain (`oxryre`, `6bnjkd`);
- Console prerequisite chain (`nikuux`, `jxqiqg`, `k3rnpw`);
- Overseer prerequisite chain (`bgs`, `gkv5z7`);
- all other tenant manifest prerequisites recorded in prior ledger audits.

The eight rollout items blocked only on corrected/closed `jtrjzk` are:

- livespec `livespec-akg7k5`
- driver-claude `livespec-driver-claude-gtqrzu`
- driver-codex `livespec-driver-codex-bedeju`
- beads-fabro `bd-ib-35qhta`
- git-jsonl `bd-gj-uworva`
- runtime `livespec-runtime-ohlb4f`
- console `livespec-console-beads-fabro-6yii4r`
- overseer `overseer-cdhdlv`

Remeasure each tenant's ledger, fetched forge state, existing corrected bump PR,
worktrees, branches, and safe Fabro runs before dispatch/adoption. Use normal
drive actions and tenant-specific AGENTS instructions. The fleet definition
covers tracked `.sh` files and Bash recipes embedded in justfiles, preserves
documented deviations, rejects accidental omissions, requires positive empty
and failing controls, and measures the full corpus.

Closeout `livespec-dev-tooling-qgw7gb` depends on all eight rollouts. Only after
all eight are closed: run fresh full-fleet measurement, verify final pins and
master CI in all nine tenants, complete `qgw7gb`, archive the plan through the
normal plan/worktree/PR path, and clean only this track's remaining worktrees and
branches.

## Workspace ownership

Do not touch the supervisor-owned jtrjzk worktree/branch above.
All other worktrees shown by `git worktree list` may belong to other sessions;
do not clean them merely because a hygiene scan calls them stale. The
`audit_sibling_groom` sub-agent was stopped during this wind-down. No durable
Fabro run was cancelled or removed.

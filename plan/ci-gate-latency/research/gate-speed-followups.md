# `just check` gate latency — remaining follow-ups

Maintainer-directed 2026-08-16, arising from the fleet-ci-runner-pool
supervisor session observing real `.15` validation gate wall-times (a
single target, `check-per-file-coverage`, at 1108.4s / ~18.5 minutes,
on this same repo's own `just check` aggregate) and asking "how can we
make this faster."

## Correction made before filing anything

The obvious first two candidates — a parallel check-aggregate
dispatcher, and a pre-push green-token short-circuit — are **already
shipped**, not new findings. `livespec-dev-tooling-7us` (epic,
2026-06-12, "Agent-loop + enforcement-suite performance") is 10/12
complete, and its children `.3` ("Parallel check-aggregate dispatcher
with core-budget cap + per-target timing") and `.4` ("Pre-push
green-token tree-hash short-circuit") are both closed. Today's own
observed shape — `check-per-file-coverage` as the single long-pole
target while the other ~65 targets finished in seconds — is the
signature of a working parallel dispatcher (wall time bounded by the
slowest target, not the sum of all targets), not evidence of a serial
pipeline needing the fix proposed in `archive/research/justcheck-performance/baseline-and-research.md`.
That research doc's own proposed-items list (items 1-6) is therefore
**partially stale**: re-read it as a historical record of the
investigation, not a live TODO list, before proposing anything from it
without checking `livespec-dev-tooling-7us`'s children first.

## What's actually still open (verified against the live ledger, not recalled)

- `livespec-dev-tooling-7us.7` — "Tune pytest-xdist worker cap for
  coverage runs (verify idle-host first)." Still open, unclaimed. The
  live formula today (`justfile`'s `test_nprocs`) is `nproc / 4` for
  local (non-`hosted`-lane) runs — on this 18-core box, 4 workers. The
  June research measured `-n 8` as faster than both `-n auto`(=18) and
  implicitly slower configurations under an *idle* host, but the
  deployed `/4` divisor is deliberately more conservative than that,
  because the real environment is a shared factory host running many
  concurrent Claude Code sessions and dispatched agents simultaneously
  (verified live via `ListAgents` during today's session — dozens of
  concurrent tmux sessions, several actively dispatching their own
  `just check` runs at the same time). Today's 1108s outlier on a
  4-worker run is fresh, real evidence for this item's own
  "verify idle-host first" caveat: the same target was ~130-150s in the
  June baseline and ~1108s today, and the delta is best explained by
  concurrent host load, not a regression in the target itself. This
  item should verify the tuning choice against BOTH an idle host and a
  realistically-loaded one (today's session is a real data point),
  since the two conditions may want different answers and the current
  fleet reality is usually the loaded one, not the idle one.
- `livespec-dev-tooling-e60` — "Investigate RGR cycle latency +
  agent-session efficiency; propose Honeycomb agent observability with
  a reflect loop." Still open, unclaimed. Related to, but broader than,
  this plan's scope (it covers agent-session efficiency generally, not
  just the `just check` gate specifically) -- and interesting
  possible target-overlap with `livespec-s43svm.20` (Honeycomb/OTel
  observability for the new k8s CI infra, filed on the fleet-ci-runner-pool
  epic, sequenced after that migration's podman teardown) -- both want
  Honeycomb-based observability of the CI/agent-loop's OWN behavior;
  worth checking for a shared implementation surface when either is
  picked up, but they are NOT the same item and neither supersedes the
  other (e60 is agent-loop/RGR-cycle observability; .20 is k8s cluster
  + CI-workload infra observability).

## New finding, not covered by any existing item

**Fresh worktrees are missing `just bootstrap`, silently wasting a
full gate run each time.** Observed three separate times in one day
(2026-08-15/16, fleet-ci-runner-pool track): a brand-new
`git worktree add` followed immediately by `just gate-start -- just
check` fails on exactly one target,
`check-primary-checkout-commit-refuse-hook-installed`, with
`failure_mode: worktree_pack_absent` — the worktree's local, gitignored
`dev-tooling/` pack (`worktree-lib.sh`, `branch-protection.sh`, etc.)
was never materialized, because nothing runs `just bootstrap`
automatically when a worktree is created; it's a manual first-touch
step documented in `AGENTS.md` but easy to forget mid-dispatch. Each
occurrence burned a full ~25-30 minute gate run that could only ever
fail on that one target, then required a second full run after running
`just bootstrap` by hand. This is a "normal, recurring failure mode"
by this repo's own stated discipline (`AGENTS.md` §"Enforcement-suite
and tooling discipline": "MUST be handled automatically at its
source... never skipped") — the fix is to make worktree creation (or
the gate-run entrypoint itself, as a cheap idempotent pre-check) run
`just bootstrap` automatically rather than relying on every dispatched
agent to remember it.

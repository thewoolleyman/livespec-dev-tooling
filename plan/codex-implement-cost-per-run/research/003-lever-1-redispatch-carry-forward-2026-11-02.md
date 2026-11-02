# 003 - Lever 1: what a re-dispatch keeps today, and where its carriers go

Written 2026-11-02 by the owning seat `codex-implement-cost-per-run` (epic `livespec-dev-tooling-vspttc`).

Research 002 §7 ranked lever 1 first: a re-dispatch resumes from the prior run's work, and an item whose last run
failed on a commit gate is held instead of re-dispatched into the same wall. The coordinator agreed to start there on
2026-11-02. This note records:

- what the dispatcher already does, read from livespec-orchestrator-beads-fabro at master on 2026-11-02;
- the further measurement that splits the lever into two halves;
- where each half's carrier belongs.

Paths are relative to that repository. `C` is `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/` and
`W` is `.claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro`.

## 1. Re-dispatch cost, split by what ended the previous dispatch

The source is research 002's Q3 and Q4 join: 237 Codex implement dispatches over the 7 days ending 2026-11-02. The 51
work items dispatched more than once are ordered by start time.

| Dispatch ordinal of the item | Dispatches | Median cost | Median responses | Merged | Implement error |
|---|---:|---:|---:|---:|---:|
| 1st | 51 | $12.23 | 171 | 1 | 25 |
| 2nd | 51 | $7.71 | 118 | 21 | 12 |
| 3rd | 27 | $9.38 | 149 | 13 | 10 |
| 4th or later | 11 | $3.36 | 52 | 7 | 3 |

| What the previous dispatch's implement node did | Re-dispatches | Cost | Merged |
|---|---:|---:|---:|
| Ended in error (mostly a commit gate, research 002 §5) | 41 | $475.87 | 11 |
| Ended ok, and a later node failed | 48 | $379.45 | 30 |

The median gap between one dispatch of an item ending and the next starting is 3.3 h (p25 1.7 h, p75 6.8 h). Every
re-dispatch's minimum input per response is still the full brief. In the pre-fix regime that is a median of 130k
tokens, so nothing in the context carries over.

## 2. What exists in the dispatcher

**Recovery routing** (`C/_dispatcher_recovery_routing.py:214-240`; contracts.md, "Recovery from the failed run's
preserved work") gives a candidate one of four routes: `resume`, `seeded`, `fresh` or `held`.

- **Measured routing is narrow.** Only an item *released for recovery* is measured, which means a stall release, a
  provider-limit release or an adapter-launch release (`C/_dispatcher_recovery_release.py:59-97`).
- **Every other item goes `fresh`.** The spec says so: "An item not released for recovery is routed `fresh` without
  any remote measurement". A `fresh` route does three things:
  - it copies the old publish branch to `refs/livespec/preserved-publish/<id>/<head>` and then deletes it
    (`C/_dispatcher_publish_branch_preserve.py`);
  - it starts the new run from the default branch;
  - it carries the prior run forward only as ledger comments in the goal brief (`C/_dispatcher_goal.py:101-115`).
- **`fresh` is what both rows of the second table in §1 got.** An item whose run ended `needs_human` or
  `non_converged` and was later returned to `ready` is not released for recovery.

**`seeded`** checks out the preserved SHA in the sandbox and briefs the run as an interrupted attempt
(`C/_dispatcher_recovery_preserved.py`, `C/_dispatcher_goal_recovery.py`). It still runs the whole graph from
`start`, through `dod_gate` and `implement`.

**`resume`**, and the operator command `resume --item`, start the graph at a later node, chosen from the factory
record or the proof-record verdict. They never visit `dod_gate` or `implement` (`C/_dispatcher_resume_entry.py`,
`C/_dispatcher_resume_anchor.py`; contracts.md, "Resume from a published pull request"). This route needs an open
PR, a proof record naming an unchanged head, and fewer than 2 prior resumes.

**The hold half is ratified but not implemented.**

- contracts.md "Across-dispatch required-result progress" requires a positive committed
  `dispatcher.redispatch_no_progress_limit`. Under it, the dispatcher refuses the next claim after that many
  item-attributable attempts that fail to advance the progress high-water mark.
- The code says that "nothing in this repository implements that mechanism yet"
  (`C/_dispatcher_stall_disposition.py:66-69`).
- Ready item **`bd-ib-s5idxj`**, "Require changed approach after repeated item-attributable dispatch failures"
  (priority 2, parent `bd-ib-lrik25`, Scenario 151), carries it.

**Within one run** a second implement turn is a fresh Codex thread (`W:283-360`, `W:2206`). Its brief is the
overwritten `$GIT_DIR/livespec-implement-hook-refusal` file, which explains the restart at about 40k tokens. The Red
and Green node split with an append-only handoff file (contracts.md v262, `bd-ib-j6piwg`) is ratified, not built,
and owned by implement-test-performance. It stays out of this plan.

## 3. Decision: lever 1 has two halves, and both are relays

Both halves change code and spec that livespec-orchestrator-beads-fabro owns. Under assertion 2 each is carried by a
relay to that repository, never by a child in this tenant.

- **1a. Hold. The carrier exists: `bd-ib-s5idxj`.**
  - What this plan relays is the measurement and a priority case. 41 re-dispatches that followed an errored implement
    cost $475.87 and produced 11 merges. Their predecessors failed mostly on a commit gate (44 dispatches, $797.63,
    research 002 §5).
  - Until implement-test-performance fixes those gates, such re-dispatches are the work a no-progress hold removes.
  - No new item is filed.
- **1b. Seeded or resumed re-dispatch after ordinary failures. No carrier exists, and the spec forbids it today.**
  - Currently an item that ended `needs_human` or `non_converged` and returns to `ready` is routed `fresh`.
  - The change routes it through the same measured recovery as a released item: `resume` at the failed node when a
    published head with a proof record exists, and `seeded` from the preserved head otherwise.
  - That needs a `propose-change` against contracts.md "Recovery from the failed run's preserved work" in the
    orchestrator repository, followed by an implementation item.
  - The work it removes is bounded by the 48 re-dispatches after an implement that ended ok ($379.45). For those, a
    `resume` skips `dod_gate` and `implement` entirely. Part of the 41 after an errored implement ($475.87) is also
    in reach, where a `seeded` start keeps the Red commit and staged work instead of re-deriving them.
  - This is the upper bound. The realized share depends on how many such items have a published head and a proof
    record, which the dispatcher journal can count before ratification.

Both relays go through the coordinator (coordinator-duties §4: only the coordinator coordinates across plans). The
next carrier-map event names their ledger ids once the orchestrator side records them.

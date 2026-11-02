## The maintainer's statement of what done means

Decided by the token-spend-analysis session under coordinator-duties section 4 (the owning session decides from measured data), at the direction of the coordinator legacy-coordinator-agent (2026-11-02): Codex implement is the largest single factory spend sink, so a plan cuts its cost per run without lowering the rate at which implement runs reach a merge.

## Definition of Done assertions derived from that statement

- This plan's research decomposes Codex implement cost per run, over at least 7 days of factory implement runs, into its drivers (turns per run, input tokens per turn and how they grow across a run, cached-input share, output tokens, re-entries per work item, and runs that ended without a merge), giving each driver's share of Codex implement cost with the Honeycomb llm-spend query that reproduces it.
- Each cost lever this plan adopts is carried by a child work item or a relay to the repository that owns the code, and none duplicates the Red/Green node split or the test-gate runtime work that plan implement-test-performance (livespec-dev-tooling-sv6m5p) owns.
- Over at least 30 consecutive factory Codex implement runs after the adopted levers ship, the median Codex implement cost per run is at least 30% below the baseline in this plan's research ($11.31 per dispatch, 7 days ending 2026-11-02), and the share of those runs that reach a merge is not lower than the baseline share.
- The llm-spend Honeycomb board shows Codex implement cost per run per day, so the result of assertion 3 can be read from one panel.

# Charter: codex-implement-cost-per-run

Opened 2026-11-02 by the token-spend-analysis session (plan epic livespec-dev-tooling-6lv7ze). The coordinator
legacy-coordinator-agent ruled that whether to open this plan was the owning session's call (coordinator-duties §4),
not the maintainer's, and the session decided from the measurement below. The assertions are session-derived and are
reported to the maintainer, through the coordinator, for objection.

## Why (measured 2026-11-02 ~00:05Z, Honeycomb env livespec, dataset llm-spend, consumer.kind = factory, 7 days)

- Factory spend over 7 days: $5,425.44.
- Codex (OpenAI) implement: $2,669.60 across 236 dispatches, 49% of factory spend and $11.31 per dispatch. It is the
  largest single sink. The next is Claude implement at $526.32 (10%).
- Codex implement per day (cost, dispatches): 10-26 $781.83 / 55; 10-27 $1,107.23 / 94; 10-28 $21.93 / 2;
  10-31 $572.45 / 54; 11-01 $185.78 / 40. Cost per dispatch moves between about $4.60 and $14.20 a day, so the
  drivers vary run to run and are not yet known.
- The 2026-10-31 24-hour snapshot (research 009 of token-spend-analysis) put Codex implement at about 80% of that
  day's factory spend; the 7-day share is 49%.

## Known inputs

- The factory Codex cached-input split is still ASSUMED (CACHED_SHARE in emit_factory.py). Plan factory-spend-accuracy
  (epic livespec-dev-tooling-fwq26r) assertion 1 measures it; until then, the decomposition reports cached share as
  assumed.
- Run outcome per dispatch is factory-spend-accuracy assertion 3. Until it lands, "reaches a merge" is read from the
  ledger (the work item's PR merged) joined on livespec.dispatch.id.
- Plan implement-test-performance owns the Red/Green node split (maintainer ruling 2026-11-01) and the commit-time
  test-gate runtime. Turns spent waiting on test gates are part of this plan's decomposition, but the fix is theirs.
  Report the share to them; do not file it here.
- The deterministic-check re-base of verification (token-spend-analysis research 006, lever 7) is a maintainer
  product decision about verdict nodes, not implement cost. It is out of scope.

## Candidate levers to measure first (not yet adopted)

- Context per turn: brief and prompt size at dispatch, and repository context the worker re-reads every turn.
- Model and reasoning effort for implement, by item size.
- Re-entry and re-dispatch: runs that end partial and are dispatched again from scratch.
- Turns spent on mechanical work a deterministic tool could do: lint fix, formatting, trailer handling.

## Seat

This plan has its own seat named codex-implement-cost-per-run (coordinator-duties §8), resumed via
/livespec-orchestrator-beads-fabro:plan codex-implement-cost-per-run. Every spend figure must come from a Honeycomb
query (.ai/coordinator-duties.md §1). Query helper: ~/token-spend-report/scripts/hcq.py, credential
HONEYCOMB_MCP_API_KEY_LIVESPEC (.ai/honeycomb-query-credential.md).

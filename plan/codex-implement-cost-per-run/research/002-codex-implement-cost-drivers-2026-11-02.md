# 002 - Codex implement cost per run: measured drivers (assertion 1)

Written 2026-11-02 by the owning seat `codex-implement-cost-per-run` (epic `livespec-dev-tooling-vspttc`). This note
discharges the MEASUREMENT half of plan assertion 1. Every figure below comes from a Honeycomb query in the `livespec`
environment, run headless with `HONEYCOMB_MCP_API_KEY_LIVESPEC` through `~/token-spend-report/scripts/hcq.py`. The
query specs are in §8 so the figures can be reproduced. The forge outcome join (§5) uses `gh pr list`.

## 1. Window, population and method

- **Window:** 7 days, `2026-10-26T00:00:00Z` to `2026-11-02T00:00:00Z`. Codex served implement on 4 of those days:
  10-26, 10-27, 10-31 and 11-01. 10-28 to 10-30 ran on Claude Sonnet 5.5.
- **Population:** `llm-spend` events with `source = codex-app-server`, `spend.where = factory`, `spend.schema = 2` and
  `node = implement`. The `node != pending` filter keeps only the final, attributed copy of each response:
  `emit_factory.py` writes a provisional `pending` event, and later a `retract` plus a `restate`.
- **Unit:** one event is one Codex model response, which this note calls a "turn". A Fabro `run_turn` is one
  workflow-node turn, which is many responses. This note calls that an "implement turn".
- **Totals:** 237 dispatches, 148 work items, 39,601 responses and $2,672.65. The model was `gpt-5.6-terra` at `high`
  effort on every response, so the window holds no model or effort variation.
  - The charter quoted $2,669.60 over 236 dispatches, taken at about 00:05Z. The small difference is responses that
    were re-attributed after that read.
  - The charter's per-dispatch figure, $11.31, is a MEAN. The MEDIAN over the same window is **$8.66**. See §7 on
    what this means for assertion 3.
- **Cached share is ASSUMED.** `emit_factory.py` prices factory Codex input with `CACHED_SHARE = 0.90`, because the
  span carries no cache split. Plan factory-spend-accuracy assertion 1 owns measuring it.
  - Every token-cost figure below inherits that assumption.
  - Sensitivity: each percentage point of cached share moves Codex implement cost by about $122.6, or 4.6%. That is
    6.81 G input tokens × 1% × ($2.00 − $0.20) per million tokens.

Note on the `usd.*` component columns: over this window they sum to $2,055, not $2,672. They are missing on part of the
events. The component split below is therefore computed from the token sums and the list price
(`prices.py`: `gpt-5.6-terra` is $2.00 input, $0.20 cached input and $12.00 output, per million tokens). That
computation reproduces `SUM(cost_usd)` to the cent.

## 2. Cost per run is responses × context per response

| Component | Tokens | $ | Share |
|---|---:|---:|---:|
| Uncached input (10% of input, assumed) | 681.2 M | 1,362.33 | 51.0% |
| Cached input (90% of input, assumed) | 6,130.5 M | 1,226.09 | 45.9% |
| Output | 7.02 M | 84.20 | 3.2% |
| **Total** | | **2,672.62** | |

Input is 97% of the cost. Output averages 177 tokens per response, so output-side levers are worth at most 3%.
Reasoning-effort levers count here only in so far as they change the NUMBER of responses.

So per dispatch: **cost ≈ responses × mean input per response × $0.38 per million tokens**. The $0.38 is the blended
input rate under the 90% cached assumption.

| Per dispatch | p10 | p25 | p50 | p75 | p90 | p99 |
|---|---:|---:|---:|---:|---:|---:|
| Cost ($) | 2.1 | 4.0 | 8.7 | 15.0 | 23.8 | 53.0 |
| Responses | 38 | 63 | 133 | 236 | 332 | 716 |
| Mean input per response (k) | 103 | 137 | 175 | 192 | 202 | 222 |
| Output (k tokens) | 6.7 | 12.6 | 24.0 | 42.1 | 58.7 | 107.1 |
| Wall span of responses (min) | 14 | 26 | 55 | 95 | 136 | 311 |

**The number of responses drives the variance, not context size.**

- The correlation of cost with responses is 0.98. Its correlation with mean input per response is 0.41.
- The variance of log(cost) across dispatches is 1.237. Log(responses) carries 0.872 of it (70%), and log(mean input
  per response) carries 0.113 (9%).

Spend is not concentrated in a few outliers. The top 10 dispatches carry 17% of it, the top 24 (10%) carry 31%, and
the top 47 (20%) carry 49%.

## 3. How input grows across a run

Within a run, the input per response climbs as the transcript accumulates. At a ceiling of about 245k tokens, Codex
compacts it. The max input per dispatch has a p50 of 242k and a p90 of 245k, which is that ceiling. Two sample
dispatches, chosen near the median of 200 responses (series in §8, Q6):

- **Pre-fix shape** (`725538b8…`, 2026-10-26, 200 responses, $15.27):
  - The first response is already 200k tokens.
  - It climbs to about 240k, compacts to about 136k, and repeats. It compacted four times in 86 minutes: 237→137,
    243→136, 244→137 and 235→134.
  - It never drops below about 134k, so every response re-sends at least 134k tokens.
- **Post-fix shape** (`c9b8979b…`, 2026-10-31, 198 responses, $8.24):
  - The first response is 38k tokens. The context grows to 100k.
  - A second implement turn (a resume) restarts at 41k and grows to 160k. It never reaches the ceiling.

The two shapes split the window cleanly on the date. Every dispatch on 10-26 and 10-27 had a minimum input above 80k,
with a median minimum of 133k. Every dispatch on 10-31 and 11-01 had a minimum below 80k, with a median minimum of 39k.

| Regime | Dispatches | Responses | Mean input per response | Cost | Mean | Median | Median responses | Merge share | Cost per merge |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Pre-fix, 10-26 and 10-27 | 144 | 25,765 | 190.2k | $1,914.40 | $13.29 | $9.54 | 134 | 40.3% | $33.01 |
| Post-fix, 10-31 and 11-01 | 93 | 13,836 | 138.1k | $758.22 | $8.15 | $6.44 | 133 | 59.1% | $13.79 |

**The change sits in plan factory-context-per-turn-reduction**, epic `bd-ib-raqyki`, in livespec-orchestrator-beads-fabro.
Several changes landed between the two regimes:

- that plan's `bd-ib-coxsfu` fix, `3790b0d9f` (10-28), which moved prepare-step payloads out of the compact preamble
  echoed into every request;
- `8aa900989` (10-30), which keeps the publication-stage scripts out of the agent prompt;
- the AGENTS.md split, `0f2843a6f` (10-31).

The cause is ATTRIBUTED from timing, not isolated per commit.

- The context drop is worth about $510 over the pre-fix responses: 25,765 responses × (190.2k − 138.1k) ×
  $0.38 per million tokens.
- Median responses per dispatch did not move (134 vs 133). The cut was pure context per response.

Two consequences:

- **Context per response is already owned and partly delivered by bd-ib-raqyki.** Its assertion 2 targets a median of
  at most 100k per response on every node. This plan must not file a context lever of its own (assertion 2 forbids
  duplicates). Per-response context now carries a floor of about 38k tokens on every response: the instructions,
  tools and brief re-sent each time. That floor is 22% of input tokens in the window, and the rest is accumulated
  transcript.
- **The 7-day baseline mixes both regimes**, so a post-lever comparison against $11.31 would credit this plan with
  bd-ib-raqyki's work. See §7.

## 4. Re-entry: in-run retries and re-dispatch from scratch

**In-run implement retries.** Fabro `run_turn` spans for `fabro.node = implement` were joined to these dispatches.
All 237 dispatches matched.

| Implement turns in the dispatch | Dispatches | Merged | Cost | Share | Responses per dispatch |
|---|---:|---:|---:|---:|---:|
| 1, ended ok | 150 | 96 | $1,189.97 | 44.5% | 119 |
| 1, ended in error | 16 | 0 | $131.96 | 4.9% | 115 |
| 2, all ok | 24 | 7 | $372.63 | 13.9% | 257 |
| 2, one ended in error | 43 | 9 | $917.05 | 34.3% | 301 |
| 3, at least one error | 4 | 1 | $61.01 | 2.3% | 197 |

- Dispatches that needed a second implement turn are 30% of dispatches and **51% of cost ($1,351)**.
- They run about 2.5× the responses, and only 17 of 71 reached a merge.

**Re-dispatch of the same work item.**

- 51 of the 148 work items were dispatched more than once, 89 re-dispatches in all.
- Ordered by start time, the first dispatch of each item cost $1,817.30. **The re-dispatches cost $855.32, 32% of
  Codex implement cost.**
- Dispatches per work item: p50 1, p75 2, p90 3, p99 5.

## 5. Runs that ended without a merge

**Method.** Run outcome per dispatch is not yet in telemetry (factory-spend-accuracy assertion 3), so it is read from
the forge.

- Factory PRs use the head `feat/<work-item-id>`. Merged PRs were read from the seven repositories these work items
  live in (`gh pr list --state all --search "created:>=2026-10-25"`).
- A merge is credited to the LAST dispatch of that work item that started before the merge, and only when the merge
  landed within 48 h of that dispatch's last response.
- 18 of the 148 items have no factory PR at all.

| Outcome | Dispatches | Cost | Share | Median cost |
|---|---:|---:|---:|---:|
| Reached a merge | 113 (47.7%) | $1,043.20 | 39.0% | $5.78 |
| No merge, and the item was dispatched again later | 87 | $1,240.12 | 46.4% | |
| No merge, and no later dispatch (terminal) | 37 | $389.30 | 14.6% | |
| **All no-merge** | 124 | $1,629.42 | **61.0%** | $11.07 |

- **Total Codex implement cost per merged dispatch: $23.65.**
- 36 work items got no merge from any dispatch in the window. They cost $583.45.
- Merge share by start day: 10-26 32.1%, 10-27 45.5%, 10-31 53.7%, 11-01 66.7%.

**Why implement turns failed.** These are the `status_message` values on implement `run_turn` spans with
`run_turn.status = error`. Each dispatch is counted once, under the first category it hits in the order below.

| Cause | Dispatches | Cost | Share | Merged |
|---|---:|---:|---:|---:|
| Commit gate, hook or full suite: the Green amend was refused or wedged, a coverage, lloc or lint gate failed, the red-green-replay gate failed, or master CI was red | 44 | $797.63 | 29.8% | 9 |
| Turn timeout (14,400,000 ms or 1,800,000 ms) | 5 | $174.70 | 6.5% | 0 |
| Partial progress, scope remaining | 5 | $75.55 | 2.8% | 0 |
| Agent killed (signal 9 or 15) | 9 | $62.14 | 2.3% | 1 |

The commit-gate share is the largest single cause in this note. **This plan does not own it.** Plan
implement-test-performance (`livespec-dev-tooling-sv6m5p`) owns the commit-time test-gate runtime and the Red/Green node
split. Its measured share is sent to that plan through the coordinator, and nothing is filed for it here.

## 6. Driver shares (assertion 1)

The lenses overlap: one dispatch can be a re-dispatch, carry a second implement turn and fail on the commit gate all at
once. So the shares below are each driver's share of the $2,672.65 and are NOT additive.

| Driver | Measured share of Codex implement cost | Owner of the fix |
|---|---|---|
| Input tokens, all of them (responses × context) | 97% (output 3%) | n/a (identity) |
| Responses per dispatch: the variance of cost across dispatches | 70% of log-variance (context 9%) | this plan |
| Context per response above the post-fix ~38k floor | 78% of input tokens | bd-ib-raqyki (context) and this plan (responses) |
| Pre-fix extra context, 10-26 and 10-27, already removed | about $510 (19%) | bd-ib-raqyki, delivered |
| Dispatches that ended without a merge | 61.0% ($1,629.42) | this plan |
| … of which the item was re-dispatched later | 46.4% ($1,240.12) | this plan |
| Re-dispatches of an item, from the 2nd dispatch on | 32.0% ($855.32) | this plan |
| Dispatches with a second implement turn | 50.5% ($1,350.69) | shared |
| Dispatches whose implement turn failed on a commit gate or hook | 29.8% ($797.63) | implement-test-performance (sv6m5p) |
| 4-hour and 30-minute turn timeouts | 6.5% ($174.70) | this plan |
| Output tokens | 3.2% ($84.20) | none (too small) |
| Cached-input share | assumed 90%; ±1 point = ±4.6% | factory-spend-accuracy (fwq26r) |

**Not measurable from these datasets.** One charter driver could not be measured: the turns spent on mechanical work
a deterministic tool could do (lint fixes, formatting, trailer handling).

- `llm-spend` and `fabro` carry no tool-call content.
- A `codex-app-server` breakdown by span name over a single dispatch blew past the endpoint's 100-group limit, even
  split down to one minute. Span names there are high-cardinality.
- Measuring this driver needs a per-tool-call attribute on the `codex-app-server` spans. It stays unmeasured, and no
  lever is ranked on it.

**Also uncounted.** Over the window, $167.27 of factory Codex spend carries `node = unattributed`: responses whose
Fabro turn never landed. Some of it is implement. It is not in the $2,672.65.

## 7. What this means for the next assertions

These are findings with a recommendation. The owning seat decides them at the next step.

1. **Restate the assertion 3 baseline.** As written, assertion 3 compares a MEDIAN against $11.31, which is a 7-day
   MEAN. It also mixes the pre-fix regime that bd-ib-raqyki has already removed.
   - The comparable baseline is the post-fix median: **$6.44 per dispatch, 59.1% merge share**, over 93 dispatches on
     10-31 and 11-01.
   - Measured against it, a 30% cut means a median of at most **$4.51**. Measured against the mixed 7-day median
     ($8.66, 47.7%), a cut of the same size would be earned mostly by work that is already merged.
   - Re-wording the assertion takes a carrier-map scope event (the plan prose, "The carrier map").
2. **Candidate levers, ranked by the measured work they remove** (coordinator-duties rule F). None of them is adopted
   yet.
   1. *Re-dispatch from scratch* (46% on no-merge dispatches that were re-dispatched; 32% on re-dispatches). A
      re-dispatch could resume from the previous dispatch's branch and handoff instead of re-deriving the work.
      Separately, an item whose last failure was a commit gate could be held until that gate is fixed, rather than
      re-dispatched into the same wall.
   2. *The second implement turn* (51%). Its cost overlaps the commit-gate share, which implement-test-performance
      owns. This plan's part is the resume cost: each resume re-reads about 40k or more tokens and climbs again.
   3. *Model price.* `prices.py` lists `gpt-6.1-terra` at $1.00 input, $0.05 cached input and $5.00 output. Under
      the 90% cached assumption that is a $0.145 blended input rate against $0.38, about 62% less per token. The window
      holds no `gpt-6.1-terra` implement runs, so its effect on responses and merge share is unmeasured. It needs a
      bounded trial before adoption.
   4. *Turn timeouts* (6.5%). A 4-hour implement turn that times out produces nothing. A stall detector or a lower
      ceiling for implement would end it sooner.
3. **Relays, not children** (assertion 2 forbids duplicates):
   - Send implement-test-performance (sv6m5p) the commit-gate share: 44 dispatches, $797.63 (29.8%), 9 of them merged.
   - Send factory-context-per-turn-reduction (bd-ib-raqyki) the measured post-fix context: 138.1k mean input per
     implement response, a floor of about 38k, and compaction at about 245k.

## 8. Queries that reproduce these figures

Run each one as
`/usr/local/bin/with-livespec-env.sh -- python3 -I ~/token-spend-report/scripts/hcq.py <dataset> '<spec>'`. Every spec
uses `"from":"2026-10-26T00:00:00Z","to":"2026-11-02T00:00:00Z","limit":1000`, except Q4, Q5 and Q7, which use
`"from":"2026-10-25T18:00:00Z"` to catch turns that began before the window. `hcq.rows` splits the window whenever a
result exceeds 100 groups. Rows for one group that spans pieces are merged by key: SUM and COUNT add, MIN and MAX
combine.

Common filter `F` = `[{"column":"source","op":"=","value":"codex-app-server"},{"column":"spend.where","op":"=","value":"factory"},{"column":"spend.schema","op":"=","value":2}]`

- **Q1, by node** (llm-spend): filters `F`; breakdowns `["node","spend.correction"]`; calculations SUM `cost_usd`,
  SUM `input_tokens`, SUM `output_tokens`, COUNT, COUNT_DISTINCT `livespec.dispatch.id`.
- **Q2, implement totals by model** (llm-spend): filters `F` + `node = implement`; breakdowns
  `["spend.model","spend.effort"]`; calculations SUM `cost_usd`, SUM `usd.input`, SUM `usd.cache_read`, SUM
  `usd.output`, SUM `input_tokens`, SUM `output_tokens`, COUNT, COUNT_DISTINCT `livespec.dispatch.id`.
- **Q3, per dispatch** (llm-spend): calculated field `ts = EVENT_TIMESTAMP()`; filters `F` + `node = implement`;
  breakdowns `["livespec.dispatch.id","work.item.id"]`; calculations COUNT, SUM `cost_usd`, SUM `input_tokens`, SUM
  `output_tokens`, MIN and MAX `input_tokens`, MIN and MAX `ts`. This one query is the source for §2 to §5.
- **Q4, implement turns per dispatch** (fabro): filters `name = run_turn`, `fabro.node = implement`; breakdowns
  `["livespec.dispatch.id","run_turn.status","visit"]`; calculations COUNT, SUM `duration_ms`; `to = now`.
- **Q5, implement turn failures** (fabro): Q4's filters + `run_turn.status = error`; breakdowns
  `["livespec.dispatch.id","status_message"]`; calculation COUNT. Categorized by regex on `status_message`.
- **Q6, one dispatch's series** (llm-spend): calculated field `ts`; filters `source = codex-app-server`,
  `spend.schema = 2`, `node = implement`, `livespec.dispatch.id = <id>`; breakdowns `["ts","trace.span_id"]`;
  calculations SUM `input_tokens`, SUM `output_tokens`. Run for `725538b86ea1450e84190d552c4e7463` and
  `c9b8979b08524472aed7ccb2fd17f94b`. Deduplicate by `trace.span_id` before reading.
- **Q7, the window edge** (llm-spend): filters `source = codex-app-server`, `spend.schema = 2`,
  `node in [implement, pending]`, `spend.correction != retract`; breakdown `livespec.dispatch.id`; window
  `2026-11-02T00:00:00Z` to now. It found $0.76 of trailing responses on three in-window dispatches, so dispatches are
  not truncated by the window's end.

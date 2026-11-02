# 004 - Lever 3: a bounded gpt-6.1-terra trial for implement (design, not adopted)

Written 2026-11-02 by the owning seat `codex-implement-cost-per-run` (epic `livespec-dev-tooling-vspttc`), while relays
1a (`bd-ib-s5idxj`) and 1b (`bd-ib-m3nfnh`) wait on `bd-ib-ch44wn`.

The 00:43Z scope event deferred this trial until lever 1 had carriers. It now has them. Nothing here touches the
routing config. That config is owned by plan `factory-configurable-model-fallback-priority`. The coordinator has
asked to be told before any trial reaches it. So this note is the proposal the coordinator rules on.

## 1. What was checked

- **Availability.** The host's Codex model catalogue (`~/.codex/models_cache.json`, fetched by codex-cli 0.166.0)
  lists `gpt-6.1-terra`:
  - visibility `list`, `supported_in_api: true`, reasoning levels low to max;
  - **a 500,000-token context window**, against 272,000 for `gpt-5.6-terra`.
- **Not in the factory catalogue.** The orchestrator's `.livespec.jsonc` `model_catalog` has no `openai/gpt-6.1-terra`
  entry. "An agent, model or effort the catalogs do not list is refused before claim", so a trial needs a catalogue
  entry as well as the `acp_nodes.implement` pin.
- **Never run here.** It has never served a response on this host. An `llm-spend` breakdown of every OpenAI
  `spend.schema` 2 response from 2026-10-19 to now shows no `gpt-6.1-terra` row, local or factory. Its effect on
  responses per run and on merges is therefore unmeasured.
- **Price.** `prices.py` lists `gpt-6.1-terra` at $1.00 input, $0.05 cached input and $5.00 output per million tokens:
  - source: OpenAI pricing page, Standard tier, short context up to 272K, read 2026-10-31;
  - `gpt-5.6-terra` is listed at $2.00, $0.20 and $12.00;
  - at the assumed 90% cached share, the blended input rate is $0.145 against $0.38, which is **0.38× per input
    token**;
  - output, 3% of cost, falls to 0.42×;
  - **the catalogue entry must re-verify these rates at the source before the trial**, as every other catalogue
    entry records.

## 2. The risk the larger window brings

Research 002 §3 shows the cost shape: input grows across a run until Codex compacts it at about 245k. That ceiling is
`gpt-5.6-terra`'s, sized to its 272k window. With a 500k window and no pinned limit, the ceiling would sit near
450k. That cuts two ways:

- **Mean context per response rises.** If the post-fix mean of 138.1k grew to 250k, the per-token saving of 0.38×
  would shrink to about 0.69× per run.
- **Long-context pricing applies past 272K input tokens.** `prices.py` does not apply it. A response over that line
  would be under-reported AND cost more.

**So the trial MUST pin `model_auto_compact_token_limit` at 245000 on the implement node.** contracts.md
"Codex compaction limit" says the limit rides the node's adapter `args`, so no code change is needed. The pin keeps
both models on the same context profile, so the comparison measures the model rather than the window.

## 3. Trial design (proposed)

- **Change.** Plan factory-configurable-model-fallback-priority applies it, at the coordinator's ruling:
  - add `openai/gpt-6.1-terra` to `model_catalog`, with re-verified prices;
  - set `acp_nodes.implement` to `codex-acp` / `gpt-6.1-terra` / `high`, with the compaction limit 245000;
  - keep the `claude-sonnet-5-5` fallback.
  - `fix` and `review` stay on `gpt-5.6-terra`, so only implement changes.
- **Bound.** The trial ends at whichever comes first:
  - 20 Codex implement dispatches on `gpt-6.1-terra`;
  - 72 hours after the change lands;
  - the early-stop rule below.

  Then it reverts unless the adoption bar is met.
- **Early stop.** After 10 trial runs, revert at once if their merge share is below 40%. That is the pre-fix regime's
  40.3%, so it is clearly worse than the 59.1% baseline.
- **Measurement.** Use the existing `codex-implement-run` events (research 002 §8 Q3 shape; board panel "Codex
  implement cost per run per day"), filtered on `spend.model = gpt-6.1-terra`. Read four things:
  - median `run.cost_usd`;
  - `AVG(run.merged)`;
  - median `run.responses`;
  - `run.mean_input_per_response`.

  Compare them with the post-fix baseline: $6.44 median, 59.1% merged, 133 median responses, 138.1k mean input per
  response.
- **Adoption bar.** Median cost per run at or below $4.51 (assertion 3's target), and merge share at or above 59.1%.
  - Per-token price alone predicts about $2.45 if responses and context are unchanged ($6.44 × 0.38).
  - So the bar leaves room for the new model to need up to about 1.8× the responses.
- **Interaction with lever 1.** The trial does not wait for relays 1a and 1b. Both change WHICH runs happen
  (re-dispatches), not the cost of a single run, so they are separable.
  - Pin the attribution: a trial run is labelled by `spend.model` and not by date.
  - Assertion 3's final reading still comes after both relays ship.

## 4. A finding for factory-spend-accuracy, not this plan

The same breakdown measured the cached-input share where Codex records it, which is local sessions only. The factory
emitter assumes 0.90.

| Local model and effort | Cached share of input |
|---|---:|
| gpt-5.6-terra high | 70.0% |
| gpt-6.1-sol high | 98.1% |
| gpt-6.1-sol medium | 78.4% |

Local interactive sessions are a weak proxy for factory runs, so this does not establish the factory's share. But the
0.90 figure came from local Codex sessions (`emit_factory.py` CACHED_SHARE comment), and the local `gpt-5.6-terra`
reading is now 70%.

At 70% the factory implement window of research 002 would cost about $5,125, not $2,673. Each point is about $122.6
(research 002 §1).

This is plan factory-spend-accuracy's assertion 1 (epic `livespec-dev-tooling-fwq26r`), and it goes there through the
coordinator. It does not change this plan's levers, because every lever here scales with input tokens whatever the
cached share. It does change every dollar figure in this plan by the same factor.

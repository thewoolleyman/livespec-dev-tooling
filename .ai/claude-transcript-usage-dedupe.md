# Claude transcripts repeat usage per content block — dedupe by message id

A Claude Code transcript (`~/.claude/projects/<slug>/<session>.jsonl`, and
`<session>/subagents/*.jsonl`) writes ONE model response as SEVERAL
`type: assistant` records, one per content block (thinking, text, each tool
call). Every one of those records carries the SAME `message.usage`. A scan that
sums `usage` over records counts each response once per block.

## What it cost (2026-10-26)

An ad-hoc scan sized the host-side `claude -p` judges for plan
`token-spend-analysis` and the new plan `anthropic-burn-mitigation` in the
livespec-orchestrator-beads-fabro repository. It summed every assistant
record:

| Figure | Summed per record | Deduped by `message.id` |
|---|---|---|
| Spec-stated judge, median input tokens per session | 875,054 | 437,918 |
| `claude -p` spend, sessions active in the last day | $1,669.79 | $816.11 |
| Opus-4.8 judge rate after R47, orchestrator cwd | ~$97.6/h | $52.4/h |

The inflated median reached a plan's Definition of Done before the capacity
coordinator caught it (routing R64). Nothing errored: each record is valid, and
only the sum is wrong.

## How to apply

- Keep a seen-set of `message.id` (fall back to the record `uuid`) and skip a
  record whose id was already counted, BEFORE adding its usage or cost.
- The `livespec/llm-spend` Honeycomb dataset is already deduped: its emitter
  keys each response on `message.id` plus `requestId`. Prefer it to a fresh
  transcript scan when it has the columns you need.
- A first-prompt CHARACTER count is per session, not per record, so it is not
  inflated. Do not "dedupe" it.

# Account attribution build (2026-10-25)

This note records how assertions 5–10 of research 004 were built on the vps, and what the build found. Everything lives under
`~/token-spend-report/` (user `ubuntu`) and in the `livespec` Honeycomb environment. No repository code changed.

## Assertion 5 kept as written

The 16:50Z handoff proposed rewording assertion 5 so that `agent-activity/metrics` would be the source for local Claude. This
unattended resume did not take that proposal, for two reasons:

- An unattended session must not reword an assertion derived from the maintainer's words.
- The one-dataset shape turned out to be buildable.

`livespec/llm-spend` now carries every response, from both the factory and this host, with `spend.account`,
`spend.account_source`, `spend.consumer`, `consumer.kind`, the model and effort, tokens, `cost_usd` and `sent_at`.

| Source | Emitter | Account from | Schema |
|---|---|---|---|
| Local Claude Code transcripts | `emit_spend.py` | `agent-activity/metrics` `claude_code.cost.usage` → `session.id` + `user.email`, per 5-minute bucket (calculated field `INT(DIV(EVENT_TIMESTAMP(), 300))`); email → caam profile via each vault profile's `.claude.json` | 2 |
| Local Claude, no telemetry (headless `sdk-cli`) | `emit_spend.py` | caam selection at that time (`spend.account_source=caam-selection`), after a 30-minute hold | 2 |
| Local Codex sessions | `emit_spend.py` | host ChatGPT account (`~/.codex/auth.json`) | 2 |
| Factory Codex (`codex-app-server` `handle_responses`) | `emit_factory.py` | host ChatGPT account; model, effort and node from the `fabro` `run_turn` span covering it | 2 |
| Factory Claude (`claude-code` `claude_code.llm_request`) | `emit_factory.py` | caam selection at that time | 6 |
| caam reads (`state.json`) | `emit_caam.py` | the read's own profile; `caam.drop_*` since the previous read | 5 |

Schema 6 is separate from schema 2 because the board's USD pies already price factory Claude in place from `claude-code`.
The account panels read schemas 2 and 6. The node pies read schema 3, which is unchanged except that it now carries the account.

## Findings

- **Accounts run concurrently.** In one 3-hour window, local sessions spent on five Anthropic accounts at once. A session keeps
  its credential across caam rotations. Attribution by "the account caam had active at the time" is therefore wrong for local
  sessions; the per-session telemetry is the truth.
- **A first attribution used 1-hour slices.** It put $11.86 that `anthropic-5` had spent on `anthropic-1`. The fix moved to
  5-minute buckets and sent retract/restate pairs (`spend.correction`). After that, 15:37:29Z–16:16Z matched the metric per
  account: `anthropic-6` $167.46 here against $168.43 there.
- **The drift judge stopped exporting telemetry.** From about 17:00Z, the orchestrator's headless drift judge (`sdk-cli`,
  opus-4.8, ~$4.3 per call) wrote transcripts but sent nothing to `agent-activity`. Its spend is still counted, through the
  caam-selection fallback.
- **Factory Codex spend was missing.** The factory has run Codex-first since 15:35Z, and none of that spend reached
  `llm-spend` until `emit_factory.py`. Its usage spans carry no model; the `run_turn` command's `CODEX_CONFIG` does. A
  `run_turn` span is written when its turn ends, so a response is first sent as `pending` and then restated.
- **caam keeps only its latest read.** Its history now exists only because `emit_caam.py` sends each read. Reads come
  about every 30–60 minutes.

## Timers

- `token-spend-fast.timer` (new) runs every 5 minutes: `emit_spend`, `emit_caam` and `emit_factory`. It keeps the ingest lag
  under 10 minutes.
- `token-spend-local.timer` runs every 10 minutes: `emit_nodes` (self-limited to 25 minutes) and `build_board --if-changed`.

The MCP key's 100 queries per hour are shared with the dispatcher's reflector. The fast tick costs about 2–3 queries, and
`run_turn` is read at most every 15 minutes.

## Triggers

Six Honeycomb triggers named `token-spend source quiet: …` email the maintainer (recipient `jKw2EyfLJ3W`). Each fires when
`COUNT < 1` over its stated threshold:

| Source | Threshold |
|---|---|
| Local emitter | 1 hour |
| Local account attribution | 1 hour |
| Factory Codex spans | 3 hours |
| Factory Claude spans | 24 hours |
| caam reads | 3 hours |
| Factory emitter | 3 hours |

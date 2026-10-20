# Query credential correction (2026-10-19)

Handoffs 2 and 3 parked this plan on a maintainer question: grant the `livespec` configuration key "Run queries" so a timer
could join dispatch sessions to Fabro stage windows. That question was never needed, and it is withdrawn.

`HONEYCOMB_MCP_API_KEY_LIVESPEC`, injected by the same `with-livespec-env.sh` wrapper, runs `run_query` through
`https://mcp.honeycomb.io/mcp` with `Authorization: Bearer`. A one-hour `COUNT` on `livespec/llm-spend` returned 646 through
it on 2026-10-19T03:5xZ. The configuration key's `queries: false` was true and irrelevant. The maintainer's correction:
"We have already dealt with the honeycomb problem before. You should have a credential somewhere that lets you do what you
need. You're probably looking at the wrong one." The general guidance now lives in `.ai/honeycomb-query-credential.md`.

## Route for assertion 3 (tokens per workflow graph node)

The method in handoff 3 stands; only the credential changes. A timer job on the vps, under the existing
`token-spend-local.timer`:

1. Queries stage windows per run: petri `fabro` `run_turn` spans carrying `fabro.node`; legacy "Stage started" / "Stage
   completed" events carrying `node_id`, mapped to a dispatch through `fabro ps -a --json` run ids.
2. Queries the `claude-code` `claude_code.llm_request` token spans per `livespec.dispatch.id` with their timestamps.
3. Assigns each token span to the stage whose window contains it, and emits per-node token events into `livespec/llm-spend`
   (idempotent, keyed on the span).
4. `build_board.py` adds 7-day and 24-hour pies grouped by node, with every factory aggregated.

The same per-node join answers the capacity coordinator's 2026-10-19 request for tokens per implement stage and per other
Claude stage, so it is built once and serves both.

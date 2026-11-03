# Honeycomb: which credential runs queries

Three Honeycomb credentials for the `livespec` environment are injected by
`/usr/local/bin/with-livespec-env.sh`. Only one of them can RUN queries.

| Variable | Surface | Can do |
|---|---|---|
| `HONEYCOMB_INGEST_KEY_LIVESPEC` | `api.honeycomb.io` events API | send events |
| `HONEYCOMB_CONFIG_KEY_LIVESPEC` | `api.honeycomb.io` REST, `X-Honeycomb-Team` | boards, columns, triggers — `queries: false` |
| `HONEYCOMB_MCP_API_KEY_LIVESPEC` | `https://mcp.honeycomb.io/mcp`, `Authorization: Bearer` | every Honeycomb MCP tool, including `run_query` |

To run a query with no browser and no interactive session — a timer job, a
script, a headless reflector — send a JSON-RPC `tools/call` for `run_query` to
the MCP endpoint with the MCP key. The working pattern is
`plan/archive/factory-success-rate-remediation/research/data/hctool.sh` in the
`livespec-orchestrator-beads-fabro` repository; the dispatcher's reflector uses
the same key (`_dispatcher_reflector_oob.py`).

## The REST Query Data API is not available here: do not ask the maintainer for it

The team is on Honeycomb's **Pro** plan. Honeycomb's REST Query Data API, which needs the "Run Queries" permission on a
configuration key, requires the **Enterprise** plan. Being on a paid plan is not enough. The maintainer cannot enable
it, so `queries: false` on the configuration key is permanent, not a setting someone forgot. The maintainer, 2026-11-02:
"I can't enable run queries, I am on a pro plan, not an enterprise plan ... so you stop asking me."

Every query, from an agent or from a deterministic script, therefore goes through the MCP endpoint with the MCP key
(below). The endpoint is plain HTTPS with JSON-RPC, so a script can call it with no LLM involved. Its budget is about
100 queries per hour, shared with the dispatcher's reflector, so a recurring script runs a small fixed query set and
caches the results.

Two traps:

- `GET https://api.honeycomb.io/1/auth` answers `unauthenticated` for the MCP
  key. That endpoint does not accept it; the key is not dead.
- Seeing `queries: false` on the configuration key is NOT a reason to ask the
  maintainer for an account permission change. On 2026-10-18 a session parked
  plan `token-spend-analysis` on exactly that question; the maintainer's answer
  was that the problem had already been solved and the session was reading the
  wrong credential.

Before calling any credential insufficient, list every name the wrapper injects
(`with-livespec-env.sh -- env | cut -d= -f1 | grep -i honey` — names only, never
values) and grep the fleet repositories for how each one is used.

## Two traps when you run the query helper

The helper is `~/token-spend-report/scripts/hcq.py`. Both of these traps were measured on 2026-11-02 by plan
codex-implement-cost-per-run.

- **Do not read results from the wrapper's stdout.** Run as
  `with-livespec-env.sh -- python3 hcq.py ... > file`, the JSON in the file stopped mid-record at about 3 KB. The
  command reported no error, and the file would not parse. Instead, have Python write the result itself:
  `json.dump(hcq.rows(dataset, spec), open(path, 'w'))`.
- **A breakdown over 100 groups spends the query budget fast.** When a result has more than 100 groups, `hcq.rows`
  splits the time window into as many pieces as the reported row count needs, at 85 groups a piece, and repeats on
  any piece that still overflows. A caller that passes `hint=` also stores its groups per second in
  `state/hcq-density.json`, and the next call pre-splits from it instead of paying for the overflowing first query.
  The cost of a per-span breakdown is still about one query per 85 spans, whatever the cadence. That key's budget is
  about 100 queries per hour, shared with the dispatcher's reflector. Breaking `codex-app-server` down by span `name`
  for a single dispatch spent a large part of it. Narrow a breakdown before you widen its window.

## Counting what a script spends

`hcq.py` appends one line per `run_query` call to `~/token-spend-report/state/hcq-calls.jsonl`, with the time, the
calling script, the dataset, the window and the breakdowns. Read that file first to attribute calls. Use
`~/token-spend-report/measure/` to measure the whole host, including callers that do not use `hcq.py`.
`mcpq-run.sh <log>` counts `run_query` writes through libssl with a bpftrace uprobe, and `sni-run.sh <log>`
counts TLS ClientHellos to `mcp.honeycomb.io` with tcpdump. Each runs for one hour. Before trusting either count,
fire one control query and check that both logs show it. Stop the probes by their own process ids, not with
`pkill -f`. On 2026-11-03 the token-spend timers were measured at 133 of 139 queries in an hour. Plan
token-spend-analysis note 010 records that measurement and the fix.

To count factory Codex implement spend in `llm-spend`, filter on all four of these:

- `source = codex-app-server`
- `spend.where = factory`
- `spend.schema = 2`
- `node = implement`

The `node` filter drops the provisional `pending` rows and the `retract` rows, so only the final, attributed copy of
each response is counted.

The `usd.*` component columns are missing from some events. Recompute the component split from the token sums and
`prices.py`.

The per-run rollup is `kind = codex-implement-run`, sent by `emit_codex_runs.py`. Read cost per run from that event
rather than summing responses yourself.

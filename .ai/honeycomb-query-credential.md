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
  splits the time window in half and queries each half, repeating until every piece fits. A high-cardinality
  breakdown can therefore spend many of the MCP key's 100 queries per hour before it gives up. That key is shared with
  the dispatcher's reflector. Breaking `codex-app-server` down by span `name` for a single dispatch did exactly this.
  Narrow a breakdown before you widen its window.

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

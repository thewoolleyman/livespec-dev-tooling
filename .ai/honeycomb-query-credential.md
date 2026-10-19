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

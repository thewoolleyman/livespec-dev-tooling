# Measured MCP-key query rate of the other callers (2026-11-03)

This note is the measurement source for `MAX_QUERIES_PER_TICK` in
`livespec_dev_tooling/radar_honeycomb_models.py` (work item
livespec-dev-tooling-mauiu5). It replaces the design-cost citation, which
gave 28–40 queries per hour and had not been measured.

## What is shared

The Honeycomb MCP key `HONEYCOMB_MCP_API_KEY_LIVESPEC` allows about 100
queries per hour. Other callers already use it: the token-spend timers in
`~/token-spend-report`, the dispatcher's reflector, and interactive sessions
running `hcq.py`. The radar's per-tick budget is whatever those callers
leave.

## Method

Both probes ran on the dev host (`vmi3006760`) for one hour each:

1. **Primary count.** A `bpftrace -B line` uprobe on `SSL_write` and
   `SSL_write_ex` in `/lib/x86_64-linux-gnu/libssl.so.3`. It counts TLS
   writes whose payload contains `"run_query"`, and logs the pid, parent pid
   and command line of each. Before each window, a fake `run_query` POST
   from `/usr/bin/python3` confirmed that the probe catches calls. That
   positive control is excluded from every count below.
2. **Cross-check.** A `tcpdump` of TLS ClientHellos to port 443 naming
   `mcp.honeycomb.io`, from any client. It also sees Python builds that
   bundle their own OpenSSL, which the uprobe misses.

## Results

| Window (UTC) | Condition | bpftrace `run_query` | tcpdump ClientHellos |
|---|---|---|---|
| 2026-11-03 15:47:21 – 16:47:28 | before the token-spend cut | 139 (133 from the token-spend timers) | 152 |
| 2026-11-03 17:18:13 – 18:18:15 | after the cut, cold caches | 45 from the timers, plus 1 other | 69 |
| 2026-11-03 18:20:26 – 19:20:29 | after the cut, warm caches (steady state) | 29, all from the timers | 34 |

The first window was measured by the radar seat. The second and third were
measured by the token-spend-analysis seat with the same probes. In the third
window, the timers' own audit log also recorded 29 calls (emit_factory 26,
emit_nodes 2, emit_spend 1).

Steady state, per hour:

- 34 queries from all clients (the tcpdump figure; bpftrace's 29 are a
  subset).
- `emit_codex_runs` adds about 8 queries every 4 hours, or about 2 per hour.
- Total for the other callers: about 36 per hour.
- emit_factory scales with factory activity, at about 1 query per 85 spans.

Shape: the timers send one burst of about 27 calls at :07–:08 past each
hour, lasting about 70 seconds. The worst 10-minute bucket is about 35
calls, when that burst coincides with emit_codex_runs.

## Derivation

Reserve 40 queries per hour for the other callers. That is the measured 36
per hour, rounded up for emit_factory's dependence on factory activity. The
key's 100 per hour then leaves 60 per hour for the radar, or 15 queries for
each of the four 15-minute ticks in an hour.

`MAX_QUERIES_PER_TICK = 15` therefore stands. What changes is its citation,
which must name this measured figure, its window and this note as the
source.

Re-measure with the same probes if a new caller starts using the key, or if
emit_factory's share grows with factory throughput.

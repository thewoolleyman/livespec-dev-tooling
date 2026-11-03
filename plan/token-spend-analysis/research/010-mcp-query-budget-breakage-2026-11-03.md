# MCP query budget breakage, measured and fixed (2026-11-03)

On 2026-11-03 legacy-coordinator-agent reopened this plan's seat for a breakage. The scripts behind this plan's
timers, in `~/token-spend-report`, were using up most of the Honeycomb MCP query key's budget of about 100
`run_query` calls per hour. The dispatcher's reflector shares that key. The fix had to bring the timers to a
measured ceiling that leaves at least half the budget to other callers.

## How it was measured

The radar-and-deterministic-admission seat supplied the method, and the same method was used before and after the
fix. The scripts are kept in `~/token-spend-report/measure/`.

- **bpftrace:** `mcpq.bt` puts a uprobe on libssl `SSL_write` and counts `run_query` writes, along with the calling
  command line. `mcpq-run.sh` runs it for one hour. It needs `bpftrace -B line`.
- **tcpdump:** `sni-run.sh` counts TLS ClientHellos to `mcp.honeycomb.io` for one hour. This catches every client
  and every TLS library, so it reads at or above the bpftrace count.
- **Audit log:** `hcq.py` now appends every call to `state/hcq-calls.jsonl`. Each line records the time, the
  calling script, the dataset, the window and the breakdowns.

Each after-window began with one positive-control query, and every source caught it. The figures below leave it out.

## Figures

| Window (UTC) | bpftrace | tcpdump | From the timers | Per-10-min buckets (bpftrace) |
|---|---:|---:|---:|---|
| Before: 15:47-16:47, fast timer every 5 min | 139 | 152 | 133 | 14, 17, 6, 44, 26, 31, 14 |
| After, cold run: 17:18-18:18 | 46 | 69 | 45 | 0, 0, 1, 0, 45, 0 |
| After, warm run: 18:20-19:20 | 29 | 34 | 29 | 2, 0, 0, 0, 27, 0 |

Notes on the after-windows:

- **The cold window** held the first hourly run under the new code. That run had no stored densities and an empty
  turns cache, so it made 43 `emit_factory` calls and 2 `emit_spend` calls. The one other bpftrace call in that hour
  was another session's ad-hoc query. Most of the gap between tcpdump and bpftrace (18 ClientHellos at 17:50-17:59Z)
  came from a client that does not use libssl, not from the timers.
- **The warm window** held 29 calls:
  - `emit_factory` 26: codex 17, claude 4, fabro 5;
  - `emit_nodes` 2;
  - `emit_spend` 1.
- **`emit_codex_runs` ran in neither window.** It now makes about 8 calls every 4 hours, roughly 2 per hour on
  average.
- **Steady state:** about 31 calls per hour from the timers. The worst 10-minute bucket is about 35 calls, when the
  hourly burst and a codex-runs pass fall in the same bucket. That leaves about 69 per hour for other callers.

## Root causes

The audit log attributed the before-load as follows.

- **`emit_factory`, every 5 minutes.**
  - About 9 codex queries per run. The re-read window overlapped the last run by 900 s and held more than 100
    groups, and `hcq.rows` cut it in half over and over until each piece fit.
  - 1 claude query per run.
  - About 10 fabro turn queries every 15 minutes, because the whole 6.3 h pending window was re-read each time.
- **`emit_nodes`, every 25 minutes.** About 13 queries per run, to re-read the session window.
- **`emit_codex_runs`, hourly.** 8 queries per run.

## Fixes

The fixes are in `~/token-spend-report`, commits `d05c032` and `318f441`, with originals in
`state/bak-mcp-budget/`.

- **Maintainer ruling, relayed by the coordinator: "no need to run it every 5 minutes, run it every hour."**
  `token-spend-fast.timer` is now `OnCalendar=*:07`, in both the tracked and the installed unit, and the user units
  were reloaded with `daemon-reload`.
- **Splitting in `hcq.rows`.**
  - An overflowing window is split straight into `ceil(rows / 85)` pieces, rather than halved again and again.
  - A caller that passes `hint=` stores its groups per second in `state/hcq-density.json` and pre-splits from it on
    the next call.
- **`emit_factory`.**
  - The overlap is now 120 s, down from 900 s. Codex response spans last at most about 0.4 s and Claude spans at
    most about 32 s, so 120 s still covers late spans.
  - Fabro turns are cached in `state/emit-factory-turns.json`. Each run reads only the turns that ended since the
    cache's `until` minus 600 s, filtered on a calculated end-time field.
- **`node_join.sessions`.** Sessions are cached in 2 h buckets aligned to UTC. Settled buckets are reused, and only
  the unsettled ones are queried: a warm call takes 1-2 queries, down from 13.
- **Run intervals.** `emit_nodes` is gated to run hourly (`MIN_INTERVAL = 3300`). `emit_codex_runs` runs every 4
  hours (`EVERY = 4 * 3600`).
- **Consequences, accepted by the coordinator.**
  - DoD assertion 7, the emitter cadence bound, is re-bounded from about 10 minutes to about 62 minutes: the
    one-hour cadence plus the 120 s lag allowance.
  - The two Codex value triggers, credits drawn and allowance near limit, now use a 90 min `time_range` and a 30 min
    `frequency`, so hourly readings do not make them flap. They were applied live through `build_triggers.py`; every
    trigger read `triggered=False` afterwards.

## What is left

The codex and claude reads in `emit_factory` break down per span. They therefore cost about one query per 85 spans,
however often they run, and the ceiling rises with factory activity. At this hour's span density the timers stay
under 50 per hour up to about 1.5 times today's span rate. If that headroom runs out, the next lever is to break
down by dispatch and time bucket, with token sums, instead of by span. Nothing has been filed for that.

The radar seat has the warm-hour figure. It is the input for re-deriving the per-tick constant
`MAX_QUERIES_PER_TICK` in `livespec-dev-tooling-mauiu5`.

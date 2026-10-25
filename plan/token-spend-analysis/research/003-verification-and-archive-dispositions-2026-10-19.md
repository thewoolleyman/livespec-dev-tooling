# Verification and archive dispositions (2026-10-19)

## Proof of Done

- `captured`: session ff15e906, 2026-10-19T09:33:30Z, all four assertions.
- `verified`: session fdfe2f27, 2026-10-19T16:03:48Z. This was a different session, replaying the captured steps after the dev
  host's 10:49Z power-off and 11:03Z reboot. All four assertions reproduced:
  - 7-day factory and local spend: $13,488 and $7,896.
  - The node pies: implement 8.28B tokens, proof_capture 2.77B, unattributed 1.91B, review 0.99B, and so on.
  - 131 local Claude Code responses fell in the last hour.
  - Both user timers survived the reboot (linger) and ran unattended afterwards, so the outage itself exercised assertion 4's "no
    session running".

Neither record exercised a browser view. During capture, the Chrome extension was not connected. During verification, it was not
connected and the Playwright browser timed out. Both records instead re-run the board's stored queries unchanged through the
Honeycomb MCP key, and they say so.

## The two scope deferrals, settled at archive

1. **Host-local scripts stay host-local.** `~/token-spend-report/scripts` remains operator tooling on the vps, outside any
   repository.
   - No plan assertion needs it committed.
   - The one consumer beyond the board is the capacity coordinator's hourly cap line (`burn.py`, `burn_hour.sh`). It consumes the
     printed line, not the code.
   - Should that seat want the burn measurement adopted as product code, it files that against its own epic
     (`livespec-dev-tooling-dfixhe`), where the requirement would live.
2. **gpt-6.1-sol stays at $0.** OpenAI has published no rate. The board's method-notes panel says so. Pricing it is a one-line
   change to the price table in `emit_spend.py` when a rate exists, and no plan tracks it.

## Not part of the Definition of Done, recorded for the operator

- **The 7-day node reconcile was never re-run.** The command is `emit_nodes.py --hours 168 --reconcile`, and the last attempt
  stopped at the MCP key's 100-query hourly limit. The 24-hour emitter on the timer keeps the node pies current, so only events
  older than 24 hours keep their first attribution.
- **About 12% of 7-day factory Claude tokens are `unattributed`.** Most come from dispatches on the hp-candidate Fabro server,
  which answers 502.

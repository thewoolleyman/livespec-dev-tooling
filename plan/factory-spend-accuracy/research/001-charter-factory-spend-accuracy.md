## The maintainer's statement of what done means

Yes I approve both of the proposed plans. Go ahead and, under my mandate, define whatever makes sense from your research. Get them both started and running under the coordinator's supervision.

## Definition of Done assertions derived from that statement

- Every factory Codex response the spend emitters send to the Honeycomb llm-spend dataset after the fix carries its measured cached-input token count, and its cost_usd is priced from that measured count rather than from an assumed cached share.
- Every factory Claude response sent to llm-spend after the fix carries its cache-write tokens split into 5-minute and 1-hour lifetimes, and its cost_usd prices each lifetime at its own list rate.
- Every factory spend event sent to llm-spend after the fix carries its dispatch id, the outcome of the run that dispatch belongs to, and whether a fallback model served the response, so one Honeycomb query returns a day's factory spend split by run outcome.
- The llm-spend board shows factory cost per run per day, split by run outcome.
- When the Codex quota readings, or any one of the four spend sources (local Claude transcripts, local Codex sessions, factory Codex, factory Claude), sends no event to llm-spend for 2 hours, a Honeycomb trigger fires and notifies a recipient the coordinator reads.
- The host Honeycomb query helper returns a time-series result as machine-readable rows, one row per time bucket and group, so an hourly or daily trend is answered in one query without reading an ASCII chart.

# Charter: factory-spend-accuracy

Opened 2026-10-31 by the token-spend-analysis session (attended), on the maintainer's approval of the two plans proposed
from the 2026-10-31 audit of the coordinator's token-spend work. The assertions above are SESSION-DERIVED under the
maintainer's mandate ("define whatever makes sense from your research") and are reported to the maintainer for objection.

## Why (measured 2026-10-31, Honeycomb env livespec, dataset llm-spend)

- Factory Codex is the second-largest sink: about $3.9k over 7 days, Codex implement alone about $2.5k. Today it drives
  factory cost to about $11.40 per run (the coordinator still quotes $6.68).
- Its cost is priced from an ASSUMED cache split. emit_factory.py prices factory Codex at a fixed CACHED_SHARE (0.90) and
  emit_spend.py's backfill at the local Codex share, because the factory spans carry no cached-input count. A 10-point
  error in that share moves factory Codex cost by a large fraction of its non-cached input.
- Factory Claude spans carry no 5-minute / 1-hour cache-write split, so emit_factory.py prices every cache write at the
  5-minute rate. Local transcripts carry the split; the factory side does not.
- No run outcome or fallback field exists, so the cost of failed, cancelled or reworked runs cannot be computed. The
  audit estimated about $330 of repeated failed runs on the burn-fix items themselves, but only by hand.
- The 2026-10-31 audit took about 16 minutes because time series come back only as ASCII charts from hcq.py, and a
  16-hour hole in the Codex quota readings raised no alert.

## Where the fixes live (to confirm in scoping)

- Factory span producers: the orchestrator plugin's span receiver and the Fabro sandbox shim (see
  .ai/factory-span-receiver.md); cross-repo pieces are relays to their owning track, not children here.
- Host emitters: ~/token-spend-report/scripts/emit_factory.py, emit_spend.py, hcq.py (a git repo since 2026-10-31).
- Board abHcUYvjaYf and Honeycomb triggers (build_board.py, build_triggers.py).

## Not in scope

- The gpt-6.1-sol / unlisted-model $0 pricing defect and gpt-6-luna zero-token rows: plan llm-spend-pricing-correctness.
- Who or what the spend was FOR (claude -p purpose, seats per plan): plan spend-purpose-attribution.

## The maintainer's statement of what done means

"The goal of the overall track will be to move ONE METRIC: THROUGHPUT AS MEASURED IN PRS PER REPO PER HOUR MERGED TO MAIN BRANCH AND PASSING AS GREEN. Reported as a table of each repo and its throughput, and with a corresponding honeycomb item for me to monitor real-time as the first item on the existing livespec board"

"The first thing you should do is set up the metrics gathering and honeycomb board so you can be laser focused on improving the per0-repo PR  throughput numbers."

"The permanent emitter and the panel don't necessarily have to be part of your plan. You can hand it off to a new, focused plan if that makes more sense, and then close out your plan, which was just to really get everything picked off into new plans."

## Definition of Done assertions derived from that statement

- A committed reconciler, run by an ansible-converged timer with no agent session involved, writes one event per merged pull request to Honeycomb dataset pr-throughput for every fleet repository, saying whether it merged green.
- The first panel of Honeycomb board 'livespec family — all activity' (krThv8DvcwS) shows pull requests merged green per hour by repository from that dataset, and the board is applied from a committed definition.
- For a trailing 24 h window, the panel's per-repository count for livespec-dev-tooling and for livespec-orchestrator-beads-fabro equals the count the GitHub GraphQL method of throughput-track-organization research note 003 returns.
- No session-bound stopgap emitter is running: the loop the throughput-track-organization seat started on 2026-11-13 is stopped and the reconciler is the dataset's only writer.

# Charter — throughput-metric

Opened 2026-11-14 by plan throughput-track-organization (livespec-dev-tooling-q26e3c) at the maintainer's direction (third statement above), to own the throughput track's ONE METRIC as a permanent, session-independent measurement. The assertions are SESSION-DERIVED; the first attended session confirms or re-words them.

## What exists today (2026-11-14 ~01:0xZ)

- Definition, validation and baseline: `plan/throughput-track-organization/research/003-the-one-metric-definition-and-baseline.md` (moves under `plan/archive/` when that plan archives).
- Dataset `pr-throughput` in the Honeycomb `livespec` environment: one `pr.merged` event per merged PR for 15 repositories, backfilled 7 days at 23:30Z on 2026-11-13.
- The panels are live on board `krThv8DvcwS`, applied by `ci-runner/observability/boards/apply-boards.sh` from `livespec-family-all-activity.json` (livespec-dev-tooling#4591). Known loss: the applier drops a board's `preset_filters`.
- **The feed is a STOPGAP and this plan inherits it**: `~/.local/share/pr-throughput/emit.py` on hetzner-xubuntu, already-sent set `~/.local/state/pr-throughput/emitted.json`, log `emit.log` beside it. It is run every 10 minutes by a background loop of a Claude session and dies with that session. Loop command, run from `~/workspace/livespec-dev-tooling`:
  `while true; do /usr/local/bin/with-livespec-env.sh -- python3 ~/.local/share/pr-throughput/emit.py 48 >> ~/.local/state/pr-throughput/emit.log 2>&1; sleep 600; done`
  GraphQL only, 44 points a pass. It is the ONLY source for the panel until the reconciler converges.

## Carriers

- livespec-dev-tooling-gaetnq: the scheduled GraphQL reconciler. Refused at the spec tier at 2026-11-14T00:20:47Z: its topic `a-scheduled-graphql-reconciler-emits` has no proposal on master. kubernetes-observability (livespec-dev-tooling-s2aqob) agreed to deliver it and was filing that proposal; its conditions (GraphQL only, incremental from a watermark, points cost on its own span, cadence from measured cost, ansible-converged timer with the credential through the wrapper, idempotent into the same dataset) are on the item.
- livespec-dev-tooling-bgespb: the panel and the committed board. Mostly delivered by livespec-dev-tooling#4591; it waits on gaetnq and on livespec-dev-tooling#4594.

## Not in scope

Any lever that moves the metric. Those belong to the plans named in the track map (throughput-track-organization research notes 005 and 006).

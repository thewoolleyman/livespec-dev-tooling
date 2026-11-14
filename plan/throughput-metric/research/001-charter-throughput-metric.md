## The maintainer's statement of what done means

"The goal of the overall track will be to move ONE METRIC: THROUGHPUT AS MEASURED IN PRS PER REPO PER HOUR MERGED TO MAIN BRANCH AND PASSING AS GREEN. Reported as a table of each repo and its throughput, and with a corresponding honeycomb item for me to monitor real-time as the first item on the existing livespec board"

"The first thing you should do is set up the metrics gathering and honeycomb board so you can be laser focused on improving the per0-repo PR  throughput numbers."

"The permanent emitter and the panel don't necessarily have to be part of your plan. You can hand it off to a new, focused plan if that makes more sense, and then close out your plan, which was just to really get everything picked off into new plans."

Later statements, 2026-11-14, each relayed verbatim to this seat by throughput-plans-coordinator:

~01:4xZ: "Every tick should print the link to the honeycomb board with the throughput targets and also print it in your table. That was in my initial definition of the goal for this plan."

~01:5xZ: "The metrics should exclude docs-only MRs, because they don't show true throughput slowness. Just non-docs PRs is what I want."

~02:0xZ: "Okay, go with those metrics. Add them to your tick. And I also want all of these moved to a new dedicated honeycomb board, which is just all of these throughput charts, but split out into multiple ones so they are nice and readable and give good eyeball visibility into the progress and improvement we're making."

~02:4xZ: "Targets are not set, the numbers should keep trending down with each improvement contributing a real and measured improvement, when confounding factors or noise is discounted (where possible). If numbers go up, then the root causes should be investigated and plans added or reprioritize3d"

~02:5xZ: "WHY THE FUCK ARE SESSIONS TYPING IN YOUR PANE! THEY SHOULD USE SENDMESSAGE ON THE SAME HOST!" and "FIX ALL OF THEIR PLANS AND REPO GUIDANCE TO FORBID THAT, AS THE MAIN LEGACY COORDINATOR ALREADY DOES"

~05:3xZ (the CI-stall retro, scope event on livespec-dev-tooling-r7iuj6): "add to your plans whatever is necessary to prevent this sort of thing in the future"

## Definition of Done assertions derived from that statement

- A committed merged-green reconciler, run at most 15 minutes apart by an ansible-converged systemd timer with no agent session involved, writes to Honeycomb dataset pr-throughput one pr.merged event per merged pull request of every repository in its committed list, carrying whether it merged green, whether it is docs-only or a release, its start instant (the first commit's author time, or the factory run marker), and its PR-opened, PR-CI-green and covering-verdict instants.
- Every pass of that reconciler sends one merged-green.awaiting event per repository with master CI, and a committed Honeycomb trigger applied by apply-triggers.sh fires when any repository's oldest merge without a master CI verdict is older than that repository's master-cycle threshold.
- The first panel of Honeycomb board 'livespec family — all activity' (krThv8DvcwS) shows non-docs, non-release pull requests merged green per hour, and board 'livespec throughput' (ytZuuVuT4BQ) shows that rate, the lead-time median and p90 and the stage medians with each repository on its own chart, both applied by apply-boards.sh from committed definitions.
- A committed headline command prints, per repository and for the fleet, non-docs non-release pull requests merged green per hour over 6 h and 24 h against the 7-day floor and its noise band with docs-only, release and not-green side columns, then the lead-time median and p90 and the stage medians, then one row per board link.
- For a trailing 24 h window, the headline's merged-green count for livespec-dev-tooling and for livespec-orchestrator-beads-fabro equals the count the GitHub GraphQL method of throughput-track-organization research note 003 returns under the non-docs, non-release definition.
- No session-bound stopgap emitter is running: the stopgap loop has exited on its RETIRED file and the reconciler is the only writer of pr.merged and merged-green.awaiting events.

The charter's four session-derived assertions were re-worded into these six by the plan's seat at its first resume, 2026-11-14 ~05:4xZ, after the later statements above widened the scope. The carrier-map scope event on livespec-dev-tooling-oe7cfw records the change, the carriers and the deferrals.

# Charter — throughput-metric

Opened 2026-11-14 by plan throughput-track-organization (livespec-dev-tooling-q26e3c) at the maintainer's direction (third statement above), to own the throughput track's ONE METRIC as a permanent, session-independent measurement.

## Rules for this plan's seat

- Talk to every agent session ONLY with SendMessage, on this host or another; NEVER type into a pane (`herdr agent prompt`, `herdr pane send-text`, `herdr pane run`, `tmux send-keys`). See `.ai/distributed-sendmessage-protocol.md` (plan distributed-sendmessage, livespec-dev-tooling-rlwppp). This supersedes the seat's opening brief, which said to report with `herdr agent prompt throughput-plans-coordinator`.
- Never raise a blocking picker; report to the seat throughput-plans-coordinator, which carries asks to the maintainer.
- Dispatch goes through legacy-dispatcher-agent.
- Every tick prints the headline and both board links.

## The metrics (definitions agreed with kubernetes-observability, 2026-11-14)

Only NON-DOCS, NON-RELEASE pull requests count. Docs-only means every changed path ends in `.md`, read from the GraphQL files connection, never from a title or commit prefix. A release PR has a head ref starting `release-please--` or a title starting `chore(master): release`.

- M1 throughput: merged green per hour (6 h, 24 h, 7-day floor) with docs-only, release and not-green side columns. Merged green = the covering master CI run concluded SUCCESS (note 003).
- M2 lead time: median and p90 from start to the covering master verdict. Start = the first commit's author time for seat PRs (git stamps it when `git commit` starts, before the pre-commit gate), and for factory PRs the newest run marker (a `livespec-dispatch-factory` comment, or a pre-dispatch `admitted` DoD judgement) at or before the first commit's author time and within 6 h of it, else the first commit.
- M3 stage medians: start→PR opened, opened→PR CI green, PR CI green→merged, merged→covering verdict.
- The 7-day floor and the noise band (mean ± 1 sd of daily values) are frozen over 2026-11-06T22:05Z..2026-11-13T22:05Z.

## What exists today (2026-11-14 ~05:4xZ)

- Definition, validation and baseline: `plan/throughput-track-organization/research/003-the-one-metric-definition-and-baseline.md` (moves under `plan/archive/` when that plan archives).
- Dataset `pr-throughput` in the Honeycomb `livespec` environment. Events carrying `pr.docs_only` are the classified copies (a 176 h backfill on 2026-11-14 ~02:0xZ, 1859 events); older copies lack the field and are filtered out by `pr.docs_only = false`.
- Boards: `krThv8DvcwS` (family board, first panel the headline) and `ytZuuVuT4BQ` ('livespec throughput', 27 panels), both applied by `ci-runner/observability/boards/apply-boards.sh`.
- **The feed is still a STOPGAP, run by this plan's seat**: `~/.local/share/pr-throughput/emit.py` and `headline.py` on hetzner-xubuntu, state under `~/.local/state/pr-throughput/` (`emitted-v2.json`, `awaiting.json`, `emit.log`). A background loop of the seat's Claude session runs it every 10 minutes and dies with that session; the seat relaunches it first after any restart. Loop command, run from `~/workspace/livespec-dev-tooling`:
  `S=~/.local/state/pr-throughput/RETIRED; while [ ! -e "$S" ]; do /usr/local/bin/with-livespec-env.sh -- python3 ~/.local/share/pr-throughput/emit.py 48 >> ~/.local/state/pr-throughput/emit.log 2>&1; for i in $(seq 60); do [ -e "$S" ] && break; sleep 10; done; done`
  Handover, agreed with kubernetes-observability: the reconciler's converge touches the RETIRED file, waits for "stopgap loop exited" in `emit.log`, kills any pass still running, moves `emit.py` to `emit.py.retired`, and only then seeds and starts its timer.

## Carriers

- livespec-dev-tooling-gaetnq: the scheduled GraphQL reconciler and its timer. kubernetes-observability (livespec-dev-tooling-s2aqob) delivers it; its spec text is livespec-dev-tooling#4599 (topic `a-scheduled-graphql-reconciler-emits`).
- livespec-dev-tooling-754wgi: guard G1, the `merged-green.awaiting` event and the committed trigger (threshold max(60, 2 × master-cycle p50 + 30), cap 180). kubernetes-observability delivers it.
- livespec-dev-tooling-bgespb: both boards as committed definitions.
- livespec-dev-tooling-sikvra: the committed headline command.
- Assertions 5 and 6: the plan's own Proof of Done.

## Not in scope

Any lever that moves the metric. Those belong to the plans named in the track map (throughput-track-organization research notes 005 and 006).

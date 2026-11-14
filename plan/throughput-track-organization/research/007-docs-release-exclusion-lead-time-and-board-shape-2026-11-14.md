# The docs-only and release exclusion, lead time and the board shape (2026-11-14)

This note records the maintainer's directions of 2026-11-14 that changed the throughput metric after note 003, and the rulings that turned each direction into a definition. Note 003 counts every merged pull request, release-please included. Where this note differs from note 003, this note governs. Recorded by kubernetes-observability (livespec-dev-tooling-s2aqob), the deliverer of livespec-dev-tooling-gaetnq and livespec-dev-tooling-bgespb, and cited by spec proposal a-scheduled-graphql-reconciler-emits.

## Maintainer directions (verbatim, relayed by throughput-plans-coordinator, epic livespec-dev-tooling-r7iuj6)

- ~01:4xZ, on the headline table: every committed headline or table ends with a footer row linking the board, and its baseline column reads "baseline 7d (floor)" until numeric targets exist ("print it in your table").
- ~01:5xZ: "The metrics should exclude docs-only MRs, because they don't show true throughput slowness. Just non-docs PRs is what I want."
- ~02:0xZ: "Okay, go with those metrics. Add them to your tick. And I also want all of these moved to a new dedicated honeycomb board, which is just all of these throughput charts, but split out into multiple ones so they are nice and readable and give good eyeball visibility into the progress and improvement we're making."
- ~02:1xZ: "stacking multiple repos on the same chart is a bad idea because they have different build times. That kills the ability to eyeball progress or regression of throughput on a single repo."

## Rulings (throughput-plans-coordinator, decided and reported to the maintainer)

### The exclusion (~01:5xZ)

1. The headline counts merged-green pull requests EXCLUDING docs-only and release pull requests.
2. A pull request is docs-only when EVERY path in its changed-file list ends in `.md`. It is read from the changed-file list, never from a title or a commit prefix. A pull request with no changed file is not docs-only.
3. A pull request is a release pull request when its head ref starts with `release-please--` or its title starts with `chore(master): release`.
4. The 7-day floor is recomputed on the same definition. Over 2026-11-06T22:05Z..2026-11-13T22:05Z it is FLEET 6.90/h, against 9.73/h for all pull requests over the same window. The floor is frozen: it is the baseline, not a live figure.
5. Excluded pull requests are still emitted, and the side columns count them, so nothing is hidden.

### The metrics (~02:0xZ)

- M1, throughput: merged green per hour.
- M2, lead time from start to merged green: median and p90, never a mean.
- M3, the stage split: start to opened, opened to PR CI green, PR CI green to merged, and merged to master green. The fourth stage was added so the stages sum to the lead time.

Start is the first commit's author date. On this repository's own commits (2026-11-14) git stamps that date when `git commit` begins, BEFORE the commit gate runs: 99aa61d0's author time equals its gate's start. A rebase or amend keeps it. For a factory pull request, start is the newest run marker on its work item at or before the first commit's author time and within 6 hours of it. The bound exists because a relaunch writes no fresh dispatch: an unbounded reading put livespec-orchestrator-beads-fabro's 24-hour p90 at 6,330 minutes, where the bounded reading gives 337. A stage with an unknown end is left out, never sent as zero. A pull request whose start-to-open stage exceeds 72 hours is listed as stalled.

### The board shape (~02:1xZ)

1. No chart carries more than one repository: no stacking, no group-by-repo lines, no overlays. A fleet total is a line of its own.
2. Each high-volume repository has its own section with M1, M2 and M3. At build time those are livespec-dev-tooling, livespec-orchestrator-beads-fabro, livespec-overseer, livespec and hetzner-xubuntu-info. livespec stays charted at 0.29/h because it is the core repository.
3. The low-volume repositories go in tables, not charts.
4. A fleet section comes first.
5. Each panel has its own y-axis.

The family board `livespec family — all activity` (krThv8DvcwS) keeps ONE headline panel first, as a fleet line linking the dedicated board `livespec throughput` (ytZuuVuT4BQ). Its earlier first panel, `prs-merged-green-per-hour-by-repo`, broke down by repository and carried no docs-only or release filter. livespec-dev-tooling#4614 migrates it.

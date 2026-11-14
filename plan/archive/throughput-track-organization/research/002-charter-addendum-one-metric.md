# Charter addendum — the track's ONE METRIC (2026-11-13 ~22:1xZ)

## The maintainer's direction, verbatim

Relayed by legacy-coordinator-agent and repeated by the maintainer directly in this seat's pane, ~22:1xZ:

"The goal of the overall track will be to move ONE METRIC: THROUGHPUT AS MEASURED IN PRS PER REPO PER HOUR MERGED TO
MAIN BRANCH AND PASSING AS GREEN. Reported as a table of each repo and its throughput, and with a corresponding
honeycomb item for me to monitor real-time as the first item on the existing livespec board"

## What the coordinator asked this plan to do with it

1. Define the metric precisely and measure it: what counts as one PR merged to the main branch (a rebase-merge can
   land several commits per PR), what "passing as green" means (the main-branch CI run for the resulting head
   concluded success), and the window. Say whether Honeycomb `github-ci` (master push runs only, per
   ci-runtime-and-cost; skipped-job durations are wrapped, bug livespec-dev-tooling-bt2cnw) can compute it, or a new
   emitter or attribute is needed. Validate it against the GitHub API for at least two repositories over 24 h before
   trusting it.
2. The live Honeycomb panel, per repository, goes FIRST on the existing livespec board. Boards are committed under
   `ci-runner/observability/` in livespec-dev-tooling and owned by kubernetes-observability
   (livespec-dev-tooling-s2aqob). Assign the build to that owner as the track's FIRST deliverable and record it in
   the track map.
3. The handoff carries the baseline table (each fleet repository, PRs per hour merged green, over a stated window).
   Every lever in the ranked table states its expected effect on THIS metric.

## Consequence for this plan

The ranking criterion of the track map (DoD assertion 2) becomes expected effect on PRs merged green per repository
per hour. The measured baseline of DoD assertion 5 leads with that table. The report's own numbers (yield, cycle
time, full-suite runs, test CPU share, node pressure) become the explanatory drivers of the metric, not the goal.

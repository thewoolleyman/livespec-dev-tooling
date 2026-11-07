# Draft: the launch clone's orchestrator build moves only through an explicit roll step

Status: DRAFT for the maintainer. It has NOT been filed as a proposed change and has NOT been revised into the
specification. legacy-coordinator-agent asked for it on 2026-11-07 (~03:2xZ) and lists it under FOR THE MAINTAINER.
The maintainer chooses the direction. This file records the options and this seat's recommendation, and carries
ready-to-file text for the recommended option.

Author: claude:gmktec-factory-placement (plan gmktec-factory-placement, epic livespec-dev-tooling-me5aqz).

## The rule in question

livespec-dev-tooling spec v147 (livespec-dev-tooling#3623) added `SPECIFICATION/contracts.md` §"Fleet-wide plugin
adoption" → "#### Orchestrator roll hold". Its **Launch-clone exemption** bullet reads:

> The member whose repository is the held plugin's own source repository, livespec-orchestrator-beads-fabro, MUST be
> exempt from the held-install rule, so canary and proof-matrix runs can launch on the held build.

livespec-dev-tooling-7upzav implements v147, and its Definition of Done assertion 3 carries this exemption: "Under that
same unreleased hold, `just ensure-plugins` in the livespec-orchestrator-beads-fabro clone installs the offered held
build."

The section's opening paragraph also makes `ensure-plugins` the reconcile that every fleet clone's SessionStart hook
runs. Each clone's committed `.claude/settings.json` registers that hook with the matcher `""`, so it fires on every
SessionStart source: startup, resume, clear and compact.

Together these mean the launch clone adopts the marketplace's newest orchestrator build whenever ANY Claude Code
session in that checkout starts, resumes or compacts. That is true with or without a hold record. The launch clone
is the build the factory dispatches orchestrator work on, so the factory's orchestrator launch build changes as a
side effect of session lifecycle events, with no roll step.

## Measured instances (2026-11-07)

1. **01:29:32Z, source compact.** kubernetes-sandbox-backend's pre-restart session 79f576b0, working in
   /data/projects/livespec-orchestrator-beads-fabro, compacted. Its SessionStart hook ran
   `mise exec -- uv run --no-sync python -m livespec_dev_tooling.fleet.ensure_plugins`, and the output read
   "Plugin livespec-orchestrator-beads-fabro updated from c681f61e16f9 to 812c6bb59d02 for scope project"
   (transcript `~/.claude/projects/-data-projects-livespec-orchestrator-beads-fabro/79f576b0-….jsonl`, traced by
   legacy-dispatcher-agent). The launch clone moved from v0.297.0 to v0.298.0. At that moment v0.298.0's
   livespec-dev-tooling canary (wou75w run 01M6SPM6J3HD) was still running, so the move happened mid-canary.
2. **~03:20Z, source startup (seat restart).** legacy-dispatcher-agent's own SessionStart hook, on a restart of that
   seat in the same checkout, moved the launch clone from 812c6bb59d02 (v0.298.0) to 68e0a4999647 (v0.299.0),
   reported by legacy-coordinator-agent.

That is two moves in about two hours, through two different triggers, and neither was a roll step. Both were caught
because the dispatcher checks the LAUNCH-line version by hand. The coordinator ruled no revert for the first
(no bad run had resulted). No mechanical gate prevented either move.

## What the factory needs from the launch clone

- The held build must be launchable in the launch clone, because the v147 hold's canary and proof-matrix runs launch
  there. This is why the exemption exists.
- The launch build must not change underneath a canary in progress, or between a canary and the runs that rely on its
  verdict. A canary attests ONE build.
- Every install route installs only the marketplace's NEWEST build. `claude plugin update` updates "to the latest
  version", and `claude plugin install` takes no version or ref (measured 2026-11-06, scope event 17:59:25Z on
  livespec-dev-tooling-me5aqz). A ref pin would be host-wide, and stop-the-line forbids it. So any rule can only
  HOLD a build or ADOPT the newest; it can never install an older one.

## Options

### A. Keep v147 as is (status quo)

The launch clone adopts the newest build on every SessionStart source. Dispatcher gates (the LAUNCH-line version check,
treating the next launch on a moved build as a canary, and "use the registered build") catch moves after they happen.

- For: no spec change, and 7upzav ships as filed.
- Against: the launch build changes on unrelated session events, twice in two hours on 2026-11-07, including
  mid-canary. Detection is by hand. Each move turns the next ordinary launch into an unplanned canary.

### B. The SessionStart path never moves the launch clone's orchestrator build; an explicit roll verb does

In the livespec-orchestrator-beads-fabro clone, `ensure-plugins` installs the orchestrator plugin when it is absent,
but never updates an installed orchestrator build. A separate explicit recipe (for example
`just roll-orchestrator-launch-build`) performs the update, prints old and new build, and is run by the seat that owns
the roll step.

- For: simple, and closes both measured triggers.
- Against: it splits the v147 rule that every adoption goes through `ensure-plugins`. The roll step leaves no committed
  record of which build the launch clone should be on, so a second checkout or a fresh host cannot tell.

### C. Committed launch-build record (RECOMMENDED)

livespec-dev-tooling master carries a committed record naming the orchestrator build the launch clone may run (a
`launch_build` key in `fleet/orchestrator-roll-hold.json`, or a sibling file). In the launch clone, `ensure-plugins`
adopts a newer orchestrator build ONLY when the record names that offered build. Otherwise it leaves the installed build
unchanged and prints one line naming the installed build, the offered build and the recorded launch build. The roll
step is a pull request that changes the record: a git change, auditable, and the same GitOps shape every other fleet
change takes.

- For: closes both measured triggers. Keeps v147's single adoption path (`ensure-plugins`) and its run-time fetch of a
  committed record. Makes the launch build a durable, reviewable fact, not host-local state. Stays compatible with the
  newest-only install constraint: the launch clone advances exactly when the record names the newest build.
- Against: a roll now needs a merged PR, which adds minutes per roll. The record has to be updated before each canary
  launch. Mitigation: the PR is one line, and the roll seat already records each roll on the plan epic.

### D. Extend C to every member (orchestrator adopted only through the record, fleet-wide)

Every member's `ensure-plugins` adopts a newer orchestrator build only when a committed record names it, and the roll
hold becomes a special case.

- For: closes the member porosity too. Session starts moved livespec-dev-tooling, hetzner-xubuntu-info, homelab and
  livespec-overseer without a roll on 2026-11-06 (scope events 11:27:53Z and 19:34:05Z on livespec-dev-tooling-me5aqz).
- Against: a larger change than the measured problem. v147's hold already covers members during a held roll, and
  freely adopting the newest build outside a hold is the intended default. Recommend revisiting only if member drift
  recurs while no hold is set.

## Recommendation

**Option C.** The defect is narrow: the launch clone's build is moved by session lifecycle events. C fixes exactly that
by making the launch build a committed fact that only a reviewed change moves, and it reuses v147's own mechanism (the
run-time fetch of a committed record, and adoption only through `ensure-plugins`). B fixes the trigger but leaves the
intended launch build unrecorded. D is broader than the evidence supports today.

Consequence for livespec-dev-tooling-7upzav (ready, freeze-held): if C is chosen, revise the spec FIRST, then amend
7upzav's assertion 3 to "installs the offered held build only when the committed launch-build record names it", and add
a launch-clone assertion for the compact trigger, all BEFORE 7upzav launches. Otherwise the item ships the behaviour
this draft replaces.

## Ready-to-file text for option C

Target: `SPECIFICATION/contracts.md` §"Fleet-wide plugin adoption" → "#### Orchestrator roll hold". Replace the
**Launch-clone exemption** bullet with:

> - **Launch build.** livespec-dev-tooling's master branch MAY carry, in the roll-hold record or a sibling committed
>   record fetched the same way, a `launch_build` value naming one build of the held plugin. In the member whose
>   repository is the held plugin's own source repository, livespec-orchestrator-beads-fabro, `ensure-plugins` MUST
>   adopt an offered build of that plugin newer than the installed one ONLY when `launch_build` names the offered
>   build. Otherwise it MUST leave the installed build unchanged and print one line naming the installed build, the
>   offered build and `launch_build`. That member MUST be exempt from the held-install rule only through this value,
>   so canary and proof-matrix runs launch on the held build once the roll step names it. When no `launch_build`
>   value exists, that member MUST leave an installed build of the held plugin unchanged and MUST install the plugin
>   only when it is absent. No SessionStart source (startup, resume, clear or compact) moves the launch build.

Scenario to add in `SPECIFICATION/scenarios.md`: *the launch clone keeps its orchestrator build when a session there
compacts or restarts while the launch-build record names its current build.* Given livespec-orchestrator-beads-fabro
has build X installed and the committed `launch_build` names X. When the marketplace offers build Y newer than X and a
Claude Code session in that clone starts, resumes or compacts. Then the clone's installed_plugins.json orchestrator
record still names X, and the hook printed one line naming X, Y and the launch build.

Heading-coverage co-edit: a revise that adds the scenario's `## ` heading must add its `tests/heading-coverage.json`
entry and regenerate the debt register in the same commit (see CLAUDE.md §"Revise co-edit discipline").

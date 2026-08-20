# decision-authority-guidance — opening research note, 2026-08-20

Plan record discipline: the ledger is authoritative over this directory; plan
state, next action, and handoffs live on the ledger anchor ledger anchor `livespec-dev-tooling-ulem2v`
read through the plan timeline.

## Problem

The 2026-08-20 maintainer investigation of this repo's stall (report:
https://claude.ai/code/artifact/264f5d4f-6aec-4795-8431-b6adaa6a4dd6 ) found
this repo's always-load guidance is the thinnest in the fleet and silent on
decision authority, which amplified an escalate-everything failure mode:

1. `AGENTS.md` has five sections and no decision-authority guidance.
   `livespec/AGENTS.md` carries "When to ask, proceed, or self-resolve";
   `livespec-orchestrator-beads-fabro/AGENTS.md` carries "Drive authorized
   work to completion; do not over-ask". Sessions here never load either, and
   this repo's foreman + plan sessions converted five self-decidable
   engineering calls into standing maintainer escalations.
2. Nothing always-loaded says bare `bd` fails with "Access denied" and needs
   `/usr/local/bin/with-livespec-env.sh --`. Three sessions independently
   lost a diagnostic cycle to this on 2026-08-19/20.
3. `.ai/supervisor-protocol.md` here is the 2026-08-13 copy (15 KB) while the
   current shared role layer (livespec-overseer, 2026-08-19) is 60 KB; the
   missing text includes sections that directly counter the observed failure
   modes.

## Children (filed on the anchor as ready work items)

1. `AGENTS.md` section "Decision authority — when to ask, proceed, or
   self-resolve": port the livespec and orchestrator text as fleet-standard
   guidance; add two repo-earned lines — an unratified filter inside a check
   is conformance, not ratification; a question answerable with a
   recommendation is a finding, not a maintainer question.
2. Always-load wrapper note: bare `bd` returns Access denied; name the
   wrapper invocation in `AGENTS.md`.
3. Refresh `.ai/supervisor-protocol.md` to the current shared role layer,
   preserving repo-specific bindings.

## Route

In-session worker or factory dispatch (docs-only changesets, `docs(...)` /
`chore(...)` subjects, no Red-Green ritual).

## Out of scope (explicit deferrals)

- Foreman skill mechanics (livespec-overseer's foreman-autonomy-hardening
  plan).
- Plan-operation prose (livespec-orchestrator-beads-fabro's
  unattended-plan-operation plan).
- The 8zv3.5 / rop-railway operational rulings — recorded directly on those
  items on 2026-08-20.

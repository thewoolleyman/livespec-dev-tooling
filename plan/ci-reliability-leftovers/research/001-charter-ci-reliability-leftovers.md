## The maintainer's statement of what done means

"Unrelated work should be omitted or moved to other/new plans." (the maintainer, 2026-11-13 ~22:0xZ, on the throughput consolidation)

"If it's not related to any existing open plan extremely closely, then make a new plan.  CI runtime and cost seem like they're turning into a dump truck, but we need to rearchitect all this anyway." (the maintainer, 2026-11-09 ~19:3xZ, recorded on livespec-dev-tooling-6tgd2z)

## Definition of Done assertions derived from that statement

- Each of the twelve CI pool items and eight workflow-hygiene items ruled out of ci-runtime-and-cost on 2026-11-13 is a child of this plan and is closed, or is re-homed to a plan whose owning session accepted it.

# Charter — ci-reliability-leftovers

Opened 2026-11-14 by plan throughput-track-organization (livespec-dev-tooling-q26e3c). It exists by a ruling of legacy-coordinator-agent recorded on livespec-dev-tooling-q26e3c at 2026-11-13T23:02:44Z: when ci-runtime-and-cost (livespec-dev-tooling-ib3oe3) was narrowed to the throughput levers it owns, twenty of its open children had no home. ci-pool-provisioning-leftovers refused the twelve pool items (it is near archive and none of its assertions covers them), and the coordinator upheld that and ruled ONE new plan for all twenty. This plan is OFF the throughput track. The single assertion is session-derived.

## The twenty items (ids are livespec-dev-tooling-<id>)

- Pool items: jkwzwv, hqbbff, khlrw3, ybnep5, 73qw6g, fc4dzb, hnynfm, ncgrcb, 7crrkb, fsle5g, kzhduc, op67ed.
- Workflow-hygiene items: f3q7r7, hhflha, hnbn7z, hyeteu, 4mhpf4, apluqn, 6pozr5, 45qcgo.

They arrive from ci-runtime-and-cost by `reparent_plan_child`, run by that plan's session. An item the tool refuses (a spec-change-tier child with an unratified proposal, or one with no tier classification) stays under livespec-dev-tooling-ib3oe3 until the refusal clears; each such wait is recorded on THIS plan's epic.

## First jobs

Read each item, group them, and decide per item: do it, re-home it to a closely related open plan whose owner accepts it, or close it as no longer wanted. Write the carrier-map scope event. Seat: workspace livespec-dev-tooling on hetzner-xubuntu (not throughput-improvements), opened when the coordinator schedules it.

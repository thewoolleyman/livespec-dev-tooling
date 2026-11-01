## The maintainer's statement of what done means

"priority is getting fabro upgrade done and running on gmktec and load on kubernetes" (2026-10-22 ~22:00Z), following "that definition of done is completely outdated ... we are trying to move the factory off it [hp] completely" (2026-10-20 21:52Z).

## Definition of Done assertions derived from that statement

- Every fleet repository's committed dispatcher.default_factory resolves, through /etc/livespec/fabro-factories.json on the control node, to the gmktec factory, and no repository's resolves to hp.
- The next dispatch from each fleet repository after its cutover lists on the gmktec factory.
- `fabro --version` on the serving gmktec factory reports the current Petri-era candidate tag, and the legacy fabro-server unit on hp is stopped and disabled, with its binary and storage directory retained on disk read-only.
- A 24-hour window of gmktec factory dispatches is journaled on this plan from Honeycomb queries with successes per hour, the infrastructure-type failure share and kernel OOM kills, and the shared fleet cap equals the cap that window supports.
- hp carries no factory role in the committed fabro-hosts inventory.

## Origin

This plan was split out of gitops-fleet-capacity-monitoring (epic livespec-dev-tooling-dfixhe) during the 2026-11-01
legacy-coordinator cutover. The maintainer's design (LEGACY CUTOVER handoff on dfixhe, 2026-11-01T19:25:19Z) archives
dfixhe after its assertions and children move to owning plans that are not about coordinating or dispatching.
legacy-coordinator-agent (epic livespec-dev-tooling-6tgd2z) assigned dfixhe assertions 1, 2, 3, 5 and 6 to this plan
on 2026-11-01 ~21:5xZ. The gitops-fleet-capacity-monitoring seat is its owning seat.

dfixhe assertion 4 (a Kubernetes-sandboxed dispatch on gmktec, and Kubernetes as gmktec's default sandbox provider) is
NOT carried here. kubernetes-sandbox-backend (bd-ib-nmuyjc) took it, because its own assertions 1 and 5 already carry
it (scope event on nmuyjc, 2026-11-01T20:53:02Z).

## The maintainer's statement of what done means

The statement below is copied verbatim from dfixhe's description, where it was recorded when R667 re-pointed that plan:

"priority is getting fabro upgrade done and running on gmktec and load on kubernetes" (2026-10-22 ~22:00Z), following
"that definition of done is completely outdated ... we are trying to move the factory off it [hp] completely"
(2026-10-20 21:52Z).

## Definition of Done assertions

The five assertions are carried over verbatim from dfixhe assertions 1, 2, 3, 5 and 6, in that order. "This plan" in
assertion 4 below (dfixhe's assertion 5) now means this plan: the 24-hour journal is recorded on this epic.

1. Every fleet repository's committed dispatcher.default_factory resolves, through /etc/livespec/fabro-factories.json
   on the control node, to the gmktec factory, and no repository's resolves to hp.
2. The next dispatch from each fleet repository after its cutover lists on the gmktec factory.
3. `fabro --version` on the serving gmktec factory reports the current Petri-era candidate tag, and the legacy
   fabro-server unit on hp is stopped and disabled, with its binary and storage directory retained on disk read-only.
4. A 24-hour window of gmktec factory dispatches is journaled on this plan from Honeycomb queries with successes per
   hour, the infrastructure-type failure share and kernel OOM kills, and the shared fleet cap equals the cap that
   window supports.
5. hp carries no factory role in the committed fabro-hosts inventory.

## Status at creation (measured by kubernetes-sandbox-backend, relayed by legacy-coordinator-agent)

1. APPEARS MET. The factory registry lists only petri and mi-homelab on gmktec, and all 16 clones name petri or
   mi-homelab. The plan-level proof discharges it.
2. NOT MEASURED. It needs one `fabro ps` per repository, read on the gmktec factory after petri's launch hold lifts.
3. NOT MEASURED. It needs a privileged-host work item: stop and disable hp's fabro-server unit, keep its binary and
   storage read-only, and record `fabro --version` on gmktec.
4. NOT MEASURED. It needs a work item that journals 24 hours of gmktec dispatches from Honeycomb and sets the shared
   fleet cap to the cap that window supports.
5. NOT MET. `ansible/inventory/legacy.yml` (sandbox_hosts) and `ansible/inventory/host_vars/hp-xubuntu.yml`
   (fabro_server_instances) still name hp. It needs an inventory work item, sequenced after the hp unit is stopped
   (assertion 3).

## Next

Before filing children, record the scoping event, with a carrier map for every assertion. Then file the three
implementation children through capture-work-item, each with its own Definition of Done:

- the hp fabro-server stop and disable, which is privileged-host work;
- the 24-hour Honeycomb journal and cap;
- the inventory removal, which depends on the first.

Assertions 1 and 2 are carried by the plan-level proof.

Factory dispatch of these children goes through the petri-factory-on-gmktec / legacy-dispatcher-agent seat, never a
direct `drive impl:`.

dfixhe's research notes 001-003 and its ledger timeline hold the history. Read them before re-deriving any measurement.

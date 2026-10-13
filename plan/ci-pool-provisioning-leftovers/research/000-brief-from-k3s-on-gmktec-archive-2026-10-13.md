## The maintainer's statement of what done means

"All of the follow-up work items, existing or new, that you create should be living under epics and plans in their respective repos, either existing plans or new ones that you create. Then we will list what they are and decide whether we want to start sessions to work them or not." and "Go ahead and draft the proper definition of done in them with the context that you already have." (maintainer, 2026-10-13, on archiving the livespec repo plan k3s-on-gmktec-for-vps-usage, epic livespec-sab5gn)

## Definition of Done assertions derived from that statement

- None of the twelve artifacts that the archived plan's research note 005 section 2 found dead remains in livespec-dev-tooling, or each one that remains is shown to be used and the user is named in this plan's research.
- Each of the nineteen manual steps that note found surviving the migration (eleven recorded in vps-info, eight in fabro-hosts) is either performed by committed automation or recorded as an inventory-level precondition that a role's preflight assert checks before any change, so an apply on a host missing it fails at its start.
- `ci-runner/README.md` in livespec-dev-tooling attributes the gate-runner tier to the host it is installed on.

Origin: the livespec repository's plan `k3s-on-gmktec-for-vps-usage` (epic `livespec-sab5gn`, livespec ledger), archived 2026-10-13 after all six of its Definition-of-Done assertions were proven live and independently replayed. Its research notes move to `plan/archive/k3s-on-gmktec-for-vps-usage/research/` in the livespec repository. This plan was created at that archive to hold work the archived plan deferred, per the maintainer's direction quoted in the Definition of Done statement. The assertions were drafted by the archiving session (claude:plan-k3s-session-ae9c7217) from the archived plan's recorded scope and are open to the maintainer's revision before any child is admitted.

## Scope, as the archived plan recorded it

Deferred by the archived plan's 2026-10-11 scope event: "the Ansible migration's leftover twelve dead artifacts and nineteen surviving manual preconditions (research/005 section 2). Their current status is unverified; re-checked at archive time and either shown resolved or handed to a named follow-up." The archiving session did not re-measure them; their status is unverified and is this plan's first measurement.

## The findings this plan starts from (archived plan research note 005, section 2, livespec repository, measured 2026-09-09)

- "Twelve artifacts are already dead and eight of those are a superseded phase. `install-arc.sh`, `install-kueue.sh`, `arc/values-host-unique.yaml` and `kueue/resources.yaml` are phase-1 by-hand legs that `converge-ci-stack.sh` inlines rather than invokes, applying different values files in both cases."
- "Nineteen manual steps survive any migration. Eleven in `vps-info`, eight in `fabro-hosts`: building the Fabro binary, minting a server token file, loading a GitHub App private key into a vault, adding a `tailscale serve` mapping in another repository, pre-installing a package an installer then refuses to run without. … They must be recorded as inventory-level preconditions with a preflight `assert` per role, or the first apply on a rebuilt host fails in the middle rather than at the start."
- "The `gate-runner/` tier targets a host the plan never listed": six scripts, five systemd units and a polkit rule under `ci-runner/gate-runner/` run on the VPS, and `ci-runner/README.md`'s opening sentence attributes the tier to poweredge-xubuntu.

The full inventory is in the archived plan's `research/005-estate/` directory.

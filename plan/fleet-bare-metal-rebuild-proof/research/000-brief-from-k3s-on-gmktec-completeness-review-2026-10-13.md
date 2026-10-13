## The maintainer's statement of what done means

"All of the follow-up work items, existing or new, that you create should be living under epics and plans in their respective repos, either existing plans or new ones that you create. Then we will list what they are and decide whether we want to start sessions to work them or not." and "Go ahead and draft the proper definition of done in them with the context that you already have." (maintainer, 2026-10-13, on archiving the livespec repo plan k3s-on-gmktec-for-vps-usage, epic livespec-sab5gn). The goal this plan continues is that plan's R0, maintainer-declared 2026-09-06: gmktec-xubuntu, poweredge-xubuntu and hp-xubuntu MUST be rebuildable from bare metal, from git, scripted end to end (disk/RAID/LVM layout, base OS install, then the committed installers); the VPS is the sole exception because it pre-existed; no live host is changed by hand.

## Definition of Done assertions derived from that statement

- The committed phase0 bare-metal recipe, including its base-OS install stage, has a profile for each of gmktec-xubuntu, poweredge-xubuntu and hp-xubuntu, and no profile keeps a pre-existing operating system.
- gmktec-xubuntu is rebuilt from empty storage by the current committed procedure (the phase0 recipe, then `just ansible-apply ansible/ci-pool.yml`), with no command run by hand on the host, and rejoins the pool Ready, untainted and advertising its churn-slot capacity, with CI jobs passing on it and `just ansible-drift ansible/ci-pool.yml` reporting zero changes.
- hp-xubuntu is built from empty storage by the same procedure with its own profile before or as it joins the k3s cluster, with no command run by hand on the host.
- At poweredge-xubuntu's next planned rebuild window it is rebuilt from empty storage by the same procedure, the stale state.db is gone, and the recovery USB has booted its real hardware.
- Each host-record repository (gmktec-xubuntu-info, poweredge-xubuntu-info, hp-xubuntu-info) states how its node was last built and its current pool role, matching live state.

Origin: the livespec repository's plan `k3s-on-gmktec-for-vps-usage` (epic `livespec-sab5gn`), archived 2026-10-13. Its fifth independent completeness review (evidence id k3s-on-gmktec-completeness-2026-10-13e, 2026-10-13T09:04:15Z) found that plan's top-priority requirement, R0, carried only in part. This plan holds what remains. The assertions were drafted by the archiving session (claude:plan-k3s-session-ae9c7217) and are open to the maintainer's revision; the maintainer may instead narrow goal 0 by ruling.

## What R0 requires and what was carried

R0 (maintainer-declared 2026-09-06, above every other goal): the three pool hosts are rebuildable from bare metal, from git, scripted end to end — disk/RAID/LVM layout, base OS install, then the committed installers. Carried: the committed phase0 bare-metal recipe (`ci-runner/k3s/phase0-bare-metal/`, one procedure, one profile per node), gmktec-xubuntu's 2026-09-07 build, a --dry-run reproduction of poweredge-xubuntu's recorded layout, and the Ansible migration of the host installers.

## The gaps the review found

1. gmktec-xubuntu's operating system is not rebuilt from git. Its profile (`profiles/gmktec-xubuntu.env`) keeps the existing OS; the base-OS stage refuses to run on that profile and has never run on any host. The 2026-09-06T16:17Z session decision called gmktec's build "the from-empty-storage rehearsal", but that build kept the existing OS partitions. gmktec-xubuntu-info still says the node was "built from bare metal".
2. hp-xubuntu's bare-metal rebuild was never carried: no profile, no rehearsal, no item, no narrowing ruling. Only its disk-guard hotfix (livespec-cy2syw) and the move of its services to Ansible were carried. The livespec plan factory-worker-nodes-gitops (epic livespec-sqvj7p) is about to make hp-xubuntu a k3s node.
3. poweredge-xubuntu is recorded UNPROVEN until its next planned rebuild window (2026-09-06 session decision); livespec-dev-tooling-lr5uby carries it and moves here from plan ci-pool-provisioning-leftovers.
4. The procedure changed after gmktec's 2026-09-07 rehearsal (node provisioning became the Ansible playbook `ansible/ci-pool.yml`), so by this repository's own rule it is unproven until rehearsed again.
5. The host-record repositories are stale: gmktec-xubuntu-info's AGENTS.md still shows gmktec tainted with capacity 32 and names untainting as the archived plan's R5 work.

## The maintainer's statement of what done means

"All of the follow-up work items, existing or new, that you create should be living under epics and plans in their respective repos, either existing plans or new ones that you create. Then we will list what they are and decide whether we want to start sessions to work them or not." and "Go ahead and draft the proper definition of done in them with the context that you already have." (maintainer, 2026-10-13, on archiving the livespec repo plan k3s-on-gmktec-for-vps-usage, epic livespec-sab5gn)

## Definition of Done assertions derived from that statement

- In each fleet repository this plan's scoping event names as in scope, a git push of a new tree from the VPS runs that repository's full pre-push gate as a cluster Job and completes on a green verdict without the gate running on the VPS.
- In each of those repositories, a delegated git push from the VPS is refused when the cluster returns no verdict.
- In each of those repositories, a push made from a Fabro sandbox runs its pre-push gate locally rather than delegating it.
- A delegated push whose gate refreshed the VPS gates credential reports that refresh in its own output when the push succeeds, not only when it fails.
- Each fleet repository left out of the rollout is named in this plan's scoping event with the reason its gate stays local.

Origin: the livespec repository's plan `k3s-on-gmktec-for-vps-usage` (epic `livespec-sab5gn`, livespec ledger), archived 2026-10-13 after all six of its Definition-of-Done assertions were proven live and independently replayed. Its research notes move to `plan/archive/k3s-on-gmktec-for-vps-usage/research/` in the livespec repository. This plan was created at that archive to hold work the archived plan deferred, per the maintainer's direction quoted in the Definition of Done statement. The assertions were drafted by the archiving session (claude:plan-k3s-session-ae9c7217) from the archived plan's recorded scope and are open to the maintainer's revision before any child is admitted.

## Scope, as the archived plan recorded it

Deferred by the archived plan's 2026-10-11 scope event: "fleet-wide delegated_gate rollout beyond livespec-dev-tooling. pj7q4m opts in one repository only; per-repo rollout is reconsidered after assertions 3 and 4 are proven, at archive time as a named follow-up." Assertions 3 and 4 (a delegated VPS push gates on the cluster and completes green; a no-verdict push is refused) are proven for livespec-dev-tooling, with independent replays on PRs #2358, #2361 and #2364 and again after reboots on 2026-10-12 and 2026-10-13.

## What is known

- The switch is the per-repository `delegated_gate` setting; livespec-dev-tooling-pj7q4m made it host-aware so a Fabro sandbox push in an opted-in repository does not try to delegate, and opted in livespec-dev-tooling only.
- The gate client calls `with-gates-kubeconfig`, which refreshes `/etc/ci-runner/gates.kubeconfig` once on a rejected credential. On a green push the client prints none of the wrapper's stderr, so a successful push's own log does not show that it refreshed the credential; on 2026-10-13 the refresh was evidenced only by the VPS sudo journal (`refresh-gates-kubeconfig` invoked from the pushing worktree). The independent verifier recommended fixing that; it is assertion 4 here.
- Each repository's `just check` must be able to run inside the cluster gate sandbox (epic livespec-dev-tooling-rwmo provisioned git history, the master diff base and checkout bootstrap for livespec-dev-tooling). Which other repositories qualify is not yet measured; the scoping event records that per repository.

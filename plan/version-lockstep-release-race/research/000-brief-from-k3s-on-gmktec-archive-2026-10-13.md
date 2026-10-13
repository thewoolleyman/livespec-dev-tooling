## The maintainer's statement of what done means

"All of the follow-up work items, existing or new, that you create should be living under epics and plans in their respective repos, either existing plans or new ones that you create. Then we will list what they are and decide whether we want to start sessions to work them or not." and "Go ahead and draft the proper definition of done in them with the context that you already have." (maintainer, 2026-10-13, on archiving the livespec repo plan k3s-on-gmktec-for-vps-usage, epic livespec-sab5gn)

## Definition of Done assertions derived from that statement

- A post-merge janitor or gate run whose checkout includes release-please's release commit but not yet its tag passes `tests/spec/test_versioning_lockstep.py` while the version records still agree with each other.
- The version-lockstep test still fails a checkout in which `pyproject.toml`, the release manifest and a readable tag genuinely disagree.

Origin: the livespec repository's plan `k3s-on-gmktec-for-vps-usage` (epic `livespec-sab5gn`, livespec ledger), archived 2026-10-13 after all six of its Definition-of-Done assertions were proven live and independently replayed. Its research notes move to `plan/archive/k3s-on-gmktec-for-vps-usage/research/` in the livespec repository. This plan was created at that archive to hold work the archived plan deferred, per the maintainer's direction quoted in the Definition of Done statement. The assertions were drafted by the archiving session (claude:plan-k3s-session-ae9c7217) from the archived plan's recorded scope and are open to the maintainer's revision before any child is admitted.

## Scope

The existing work item livespec-dev-tooling-pdd6ix ("Version-lockstep test fails a checkout taken between release-please's release commit and its tag"), filed during the archived plan and never dispatched, is this plan's first child.

## The incident that re-measured it (2026-10-12)

livespec-dev-tooling-tb2az6 merged as PR #2399 (merge f4cef533). Its post-merge janitor, in a fresh checkout, failed `tests/spec/test_versioning_lockstep.py::test_the_version_records_stay_in_lockstep`: `pyproject.toml` read 1.95.11 (release commit 72e2af88 had landed) while the checkout's tags ended before `v1.95.11`, which existed on GitHub moments later. Master CI on the same commit passed, the same suite re-run in the kept janitor checkout passed (4,494 tests, 100% coverage), and `reconcile-merged` re-ran the janitor green. The red cost the item an extra reconcile and read as a defect in a healthy merge.

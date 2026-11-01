## The maintainer's statement of what done means

This is livespec-dev-tooling-tjldi2., it needs a plan made of itself using that slug

## Definition of Done assertions derived from that statement

- A run of the committed retention script removes a session scratch directory under `/tmp/claude-<uid>/<project>/<session-id>` that no running process carries in `CLAUDE_CODE_SESSION_ID` and that is older than the scratch retention period, and leaves an equally old one whose session id a running process carries.
- A run of the committed retention script removes an entry under `/tmp/pytest-of-<user>` older than the scratch retention period and leaves a newer one.
- A run of the committed retention script restores the configured retention user's ownership of root-owned paths in that user's uv cache and then runs `uv cache prune` as that user, so a cache holding a root-owned `__pycache__` under `archive-v0` prunes without a Permission denied abort.
- A run of the committed retention script holds the bulk-dump directory under its size cap by removing the oldest files first.
- The role refuses a bulk-dump directory that resolves to a tmpfs.
- A run of the committed retention script logs the free space of `/` and of `/tmp` before and after.
- A committed capacity-check script, run with `/tmp` at or above its threshold and `/` below its own, publishes one ntfy notification naming `/tmp`, its used share and its free space, and publishes none naming `/`.
- A second run of the capacity-check script inside the repeat interval publishes nothing.
- The scratch retention period, the two thresholds, the bulk-dump directory, its cap and the repeat interval are role variables documented in the role's `HOST_VARS.md` with the spec's defaults.
- `ansible/dev-host.yml` installs the capacity check's systemd timer at an interval of 15 minutes or less.
- After `just ansible-apply ansible/dev-host.yml` converges the dev host, `systemctl list-timers` lists the capacity-check timer with a next run within 15 minutes.
- One manual run of the converged retention service on the dev host logs the free space of `/` and of `/tmp` before and after.

Plan for livespec-dev-tooling-tjldi2, created 2026-11-01 ~20:5xZ on maintainer direction (priority #5), relayed by legacy-coordinator-agent: "This is livespec-dev-tooling-tjldi2., it needs a plan made of itself using that slug".

tjldi2 extends the closed livespec-dev-tooling-fj6dm5 (dev host has no standing disk retention; closed 2026-10-30, PR #2747) to the scope the 2026-11-01 incident exposed. Both were children of livespec-dev-tooling-dfixhe (plan gitops-fleet-capacity-monitoring), which is being dissolved; both are re-parented under this plan's epic.

The plan's Definition of Done is tjldi2's Definition of Done, adopted bullet for bullet on the coordinator's relay (session-derived, not confirmed with the maintainer in this session). Every assertion is carried by tjldi2.

Spec: SPECIFICATION/non-functional-requirements.md §"Dev host disk retention" at v106 (PR #3030), plus "## Scenario: dev host retention removes a dead session's scratch directory and leaves a live one" and "## Scenario: the dev host capacity check alerts when /tmp passes its threshold".

Measured 2026-11-01: / reached 98% (16 G free) and /tmp (48 G tmpfs) reached 100% at 13:50Z, breaking Bash, gates and factory launches. A maintainer-directed cleanup, other seats' deletions (fabro shared target ~182 G) and a completed uv cache prune (32.9 GiB, 20:02Z, after restoring ubuntu ownership of root-owned paths) brought / to 300 G free (56%) and /tmp to 23%. The root-owned uv writer is ansible become running the uvx-cached ansible-core interpreter (`just ansible-apply` / `ansible-check`), recorded on tjldi2.

State at creation: tjldi2's factory run 20261101T184715Z-1282252 was launched 18:47Z by a direct drive impl: call (coordinator: let it finish; future dispatch goes through petri-factory-on-gmktec, and gmktec dispatch is HELD until legacy-coordinator-agent lifts it).

# 005 — how merged CI-stack changes reach every CI host (livespec-dev-tooling-ctete5)

Recorded 2026-11-18 by a gate-job-resources hand-lane helper. Design only: no
product code, no host write. Every host fact below is a read of the committed
tree or a figure the item and its finding comment carry; none was re-measured
on a host in this pass.

## Recommendation

Choose the **post-merge apply**, run from the control node `vps`, over a timer
on `converge-ci-stack.service`. Do not build either until the two blockers
below are merged.

The reason is where the drift sits. The converge unit reads the installed tree
under `/usr/local/lib/ci-runner-k3s`. That tree is written only by the
`ci_converge_unit` Ansible role (`ansible/roles/ci_converge_unit/tasks/main.yml`
copies the artifact set, then starts the unit when a copy changed or the
unit's last Result was not `success`). A timer on the unit would re-run the
converge against the tree the last apply installed, so a merged change would
not reach the host: the timer would converge stale inputs on a schedule and
report success. Only an apply from `vps` moves merged bytes onto the hosts.
The 2026-11-18 drift (gamingpc 6, gmktec 18, hp 16, poweredge 27 changed
tasks) is that copy backlog, not cluster state.

## What triggers it, how often, within what bound

- Mechanism: a systemd timer on `vps` runs a committed wrapper every 15
  minutes. The wrapper fetches `origin/master` and compares the SHA recorded as
  last applied (a file on `vps`, written only after a drift-zero read-back
  passes) with master's tip. If no path under `ci-runner/` or `ansible/` changed
  between the two, it exits 0 and does nothing. Otherwise it runs the
  committed scoped apply described below.
- Bound: a merged change reaches every CI host within 30 minutes of merge when
  the apply succeeds (one timer interval plus the converge's own wait bound,
  `ci_converge_unit_converge_wait_seconds`). A failed apply leaves the recorded
  SHA unmoved, so the next tick retries; three consecutive failures raise a
  maintainer signal rather than retrying silently (the repo's flake rule: a
  bounded retry, each recorded).
- A merge-event trigger (a workflow) is rejected: anything under
  `.github/workflows/` needs an exemption and a label, and a runner on the
  tailnet-less GitHub side cannot reach `vps` anyway (`.ai/tailnet-posture.md`).
  The timer polls instead.

## What it must NOT apply unattended

A trigger MUST skip, and name in its report, any change to a credential-bearing
manifest. Read from the tree, these are:

- `ci-runner/k3s/phase2/gates/gates-rbac.yaml` (ServiceAccounts, token Secrets
  `gate-submitter-token` and the factory submitter's). The converge applies it
  at `converge-ci-stack.sh` line ~915.
- `ci-runner/k3s/phase2/gates/gate-credentials.yaml` (the forge Secret shape;
  its header says converge ships it and never applies it).
- `ci-runner/k3s/phase2/factory/factory-rbac.yaml` (ServiceAccounts, a token
  Secret).
- `ci-runner/k3s/phase2/factory-mi-homelab/factory-mi-homelab.yaml`
  (ServiceAccount, token Secret).
- `ci-runner/k3s/phase2/node-status-credential/node-status-patch-rbac.yaml`
  (ServiceAccount, token Secret).
- `ci-runner/observability/kueue-webhook-probe-rbac.yaml` (the probe identity).
- `ci-runner/k3s/secret-reinjection/arc-org-projector-rbac.yaml` and the
  `inject-*.service` units beside it (the ARC App credential projection, which
  NFR "ARC GitHub App credentials, one Secret per account" scopes to one
  Secret).
- The warm-cache and sccache converge's writer credential and ACL Secret
  (step 8c; `warm-cache/`, `sccache/`).

Mechanism: the wrapper diffs `last-applied..master` against that list (a
committed list file, so adding a credential manifest is one edit and a check
can assert every `kind: Secret` or token-Secret manifest is on it). A
non-empty intersection holds the whole range: it does not apply the other files
of that range either, because the role copies the tree in one step (see
vksuu2) and applying half a range would put the credential file on the host
under a timer. The hold is a maintainer signal naming the file and the owner
whose apply releases it, and the recorded SHA stays put until that owner's apply
runs. Non-credential RBAC (the scheduler, provisioner and warm-cache
ServiceAccounts) is not on the list; it carries no secret value.

## How the drift-zero read-back is taken and recorded

After the scoped apply, the wrapper runs `just ansible-drift ansible/ci-pool.yml`
(check mode, `--diff`) against the same hosts and parses the play recap. The
pass condition is `changed=0` for every role the trigger owns on every CI host
(the item's third assertion). The wrapper writes one JSON record per run on
`vps` (applied-from SHA, master SHA, per-host `changed` counts, the converge
unit Result per host, UTC time) and appends a summary comment to the item's
owning ledger entry only on a state change (first pass, first failure, hold),
never every tick. Roles outside the trigger's ownership (credential roles) are
excluded from the zero read by name and reported separately, so a held
credential never fakes a failure and never hides in a pass.

## Revert and kill switch

- Kill switch: `systemctl disable --now` of the timer on `vps`, plus a
  committed sentinel the wrapper checks first (an `apply.disabled` file next to
  the recorded SHA): the sentinel stops an apply that the timer already started
  at its next step boundary.
- Revert: a revert is a normal merge that the next tick applies. When master is
  red or the change is dangerous, disable the timer first, then revert by the
  incident path; do not roll a host by hand.
- The converge's own failure is a read: the existing role fails the apply
  naming the unit's result and journal tail, and the wrapper stops on it.

## Dependencies

1. **livespec-dev-tooling-vksuu2** (a placement-only converge target) is a hard
   dependency. Today any copy change starts the whole converge, which runs
   `kubectl apply -f gates/gates-rbac.yaml`; `converge-ci-stack.sh` has no
   per-component flag. The trigger needs the role to copy and apply placement
   and capacity files (`arc/runner-node-preference.conf` and its peers) without
   touching a credential manifest. Without it, the scoped apply has no safe
   scope and the wrapper can only hold.
2. **The NFR "Runner-pool node rebuild recipe" scale-set clause fix** (new item
   filed with this note) is a hard dependency for any recurring trigger.
   `converge-ci-stack.sh` lines ~706-730 run `helm upgrade --install` on every
   scale set on every converge, contradicting the ratified clause that an
   unchanged release MUST NOT be upgraded, decided from a digest read back from
   the live release, with a failed read forcing an upgrade. Every upgrade
   bumps the AutoscalingRunnerSet generation and re-creates listener pods, so
   a 15-minute trigger would churn every listener on every merge. Fix first.
3. Ordering: NFR fix and vksuu2 are independent of each other; both land before
   ctete5 is implemented. ctete5 itself carries a spec-change tier comment
   (the trigger and bound are not yet ratified clause text): the revise that
   states the bound ("within 30 minutes", the hold rule) precedes the build.

## What the host-captured proof runs

On `vps` and the four CI hosts, after both dependencies are on master:

1. Merge a one-line change to a placement value file; start a clock.
2. Without running any apply by hand, wait for the timer. Record the apply's
   record JSON, the time elapsed (must be at most 30 minutes), and, on each
   host, the installed file's checksum against git.
3. Read a runner pod created after the apply and show the changed value in its
   node affinity, plus `helm history` for each scale set showing no new
   revision (the NFR fix) and the listener pod ages unchanged.
4. Merge a change to a credential manifest on a scratch branch's merge range
   (or against a test copy of the list) and show the wrapper held, named the
   file, and applied nothing; then release it by the owner's apply.
5. Run `just ansible-drift ansible/ci-pool.yml`; read `changed=0` per host for
   the owned roles. Disable the timer and show no further run.

The proof runs on the live hosts, so it is `host_verified`, replayed by an
independent session per `.ai/independent-host-replay-identity.md`.

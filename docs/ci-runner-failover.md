# CI runner routing and hosted fallback

Ordinary CI for this repository routes through the `CI_RUNNER_LABELS`
repository variable, read directly at each gating job's `runs-on`:

```yaml
runs-on: ${{ fromJSON(vars.CI_RUNNER_LABELS || '["ubuntu-latest"]') }}
```

This is the same pattern the other fleet repositories on self-hosted capacity
use, and it is the posture ratified in `SPECIFICATION/constraints.md`
§"CI matrix shape".

The value is exactly one complete label set — never a mixed array. GitHub
matches *every* label in the array and does **not** retry an unmatched
self-hosted job on a hosted runner, so a partially-matching array strands the
job in the queue rather than falling back.

## Routing and reverting

- **To self-hosted**: set `CI_RUNNER_LABELS` to the target's label set. For an
  ARC scale set that is the scale set *name*, e.g.
  `["livespec-dev-tooling-k3s"]` — ARC routes by scale-set name, not by label.
- **Back to hosted**: set it to `["ubuntu-latest"]`, or delete the variable so
  the inline fallback applies.

The revert is **manual and operator-driven**. There is deliberately no
automatic health probe or runtime failover between the variable and the
routing decision, so the variable's setting together with the inline fallback
is the entire routing contract.

The inline fallback MUST name hosted capacity and never self-hosted, so that a
deleted or emptied variable leaves the merge gate on capacity that is always
present. `check-self-hosted-routing` enforces this statically, and it parses
`runs-on` values literally — routing hidden behind `needs.<job>.outputs.*` is
invisible to it, which is why the fallback literal is repeated inline at each
`runs-on` rather than resolved once into a job output.

## Why there is no automatic failover

This repository previously carried a two-probe health-check router
(`reusable-ci-runner-router.yml` plus the `ci-runner-health` composite Action)
that selected self-hosted capacity only after two healthy observations and
otherwise emitted `ubuntu-latest`. It was retired because it cannot work
against ARC scale sets, for two independent reasons:

- **ARC scale-set runners carry no labels.** `gha-runner-scale-set` runners
  register with an empty label array, so the probe's label-subset test can
  never match one. In scale-set mode the scale set *name* is the routing
  token, not a label set.
- **Scale sets run `min-runners: 0`.** An idle scale set has zero registered
  runners by design, so a pre-flight probe reads normal idleness as an outage.
  Raising `min-runners` to satisfy the probe would permanently pin node
  capacity.

Left in place, the router failed its probe on every run and silently routed
every job to hosted capacity regardless of `CI_RUNNER_LABELS` — the incident
recorded as `livespec-s43svm.23`.

## Fork safety

Fork-originated pull requests must never execute on self-hosted capacity
without review. That boundary is enforced by the repository's
**fork-PR approval requirement** (a repo setting), not by workflow logic —
the same model every fleet repository on self-hosted capacity relies on.
`check-self-hosted-routing` complements it statically by forbidding
fork-reachable and privileged triggers (`pull_request_target`, `workflow_run`,
`issue_comment`, `repository_dispatch`, `merge_group`, `workflow_dispatch`)
from reaching a gating self-hosted job; `pull_request` is allowed precisely
because the approval gate covers it at runtime.

Privileged golden-master workflows run on their own dedicated gate lane and do
not read this variable.

## Failure and recovery semantics

Routing is fixed when a job is created. If self-hosted capacity goes away
after a job is queued, that job stays queued — GitHub cannot migrate it to a
different `runs-on` target. An in-progress job that loses its runner is
reported failed or cancelled.

Recovery is operator-driven: set `CI_RUNNER_LABELS` back to
`["ubuntu-latest"]` and re-run the failed jobs, then set it forward again once
the capacity's own recovery proof is complete.

Before reaching for that revert, check whether the queue is stuck for a reason
a revert does not address. A job that sits `queued` with an empty `runner_name`
against a k3s scale set has two very different possible causes — the pool being
genuinely full, and a *wedged runner*: a pod that is `Running` and `ready=true`
to Kubernetes but permanently dead to GitHub, which makes ARC believe the scale
set already has a runner and suppresses the scale-up that would replace it. The
two present identically and have opposite fixes, and no capacity change clears
the second. `ci-runner/k3s/phase2/README.md` §"Wedged runner vs. saturation"
carries the two commands that discriminate them and the one that clears a
wedge.

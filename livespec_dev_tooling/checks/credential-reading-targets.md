# Credential-reading check targets, and what each degrades to without a credential

R4.S6 (`livespec-dev-tooling-ul61`), plan livespec `k3s-on-gmktec-for-vps-usage`
(epic `livespec-sab5gn`), design in that plan's `research/003` section H.

This enumeration exists because a delegated gate pod is a host that holds fewer
credentials than a maintainer's laptop, and several targets **report success
without performing their verification** when they cannot reach one. In the job
that authorises a push, that is a false green on exactly the checks that matter.

## How this set was derived

Not transcribed from the work-item's starting list — derived, on 2026-09-08,
and the starting list turned out to be incomplete in one direction and wrong in
another (see `check-fleet-conformance-admin` below).

```bash
# 1. every module that touches a credential at all
grep -rln 'gh api\|_gh_has_stored_credential\|GITHUB_TOKEN\|GH_TOKEN\|BEADS_DOLT_PASSWORD\|preflight_credential' \
  livespec_dev_tooling/checks/*.py livespec_dev_tooling/fleet/*.py
# 2. for each, whether it is an aggregate target and whether it carries a run lever
grep -E "^\s+check-<slug>\s*$" justfile
grep -oE 'LIVESPEC_RUN_[A-Z_]+' <module>
# 3. what the pre-push hook gate additionally skips
grep -n -A6 'hook_gate_skips=' scripts/just/check.sh
```

Re-run those three when this file is doubted. A module appearing in step 1 that
is absent from the table below is drift.

## The table

| Target | Credential | Without it | In the pre-push gate? |
|---|---|---|---|
| `check-branch-protection-alignment` | `gh`, **admin scope** to read branch protection | warned and **exited 0** | **YES**, unlevered |
| `check-master-ci-green` | `gh`, read scope | warned and **exited 0** (`"skip"`) | **YES**, unlevered |
| `check-fleet-conformance-admin` | user-class `gh` admin credential | **already fails** — see below | **NO**, `hook_gate_skips` |
| `check-fleet-conformance` | fleet GitHub App installation token | n/a — lever unset off CI | **NO**, lever never set in committed recipe/hook/env |
| `check-plan-epic-parity` | `BEADS_DOLT_PASSWORD` | self-gates | **NO**, `LIVESPEC_RUN_PLAN_EPIC_PARITY` unset |
| `check-plan-record-conformance` | `BEADS_DOLT_PASSWORD` | self-gates | **NO**, `LIVESPEC_RUN_PLAN_RECORD_CONFORMANCE` unset |
| `check-work-item-interpolation-delimiters` | `BEADS_DOLT_PASSWORD` | self-gates | **NO**, lever unset |
| `check-work-item-status-vocabulary` | `BEADS_DOLT_PASSWORD` | self-gates | **NO**, lever unset |
| `merged_branch_sweep` | `gh` | n/a | **NO**, not an aggregate target |

The levers above are set only in `.github/workflows/*.yml`. No committed recipe,
hook, or environment configuration in this repository arms any of them, so those
rows perform no verification on any host during a pre-push run and cannot
produce a false green there. **If a repository ever commits such a lever** — a
`[env]` table in `.mise.toml` would do it — that row enters the gate's set on
every host and its credential must then be provisioned to the executor. Neither
repository's `.mise.toml` carries an `[env]` table today.

## `check-fleet-conformance-admin`, read rather than assumed

`research/001` section 8 left this one open and the work-item said to read it
rather than assume it behaves like the two `gh api` checks. It does not.

`livespec_dev_tooling/fleet/fleet_conformance_admin.py` classifies its **credential
class** before evaluating any obligation row, via
`fleet/_credential_preflight.py`. A row it cannot see becomes **BLIND and is
reported at ERROR severity**, not warned and passed. That module's own docstring
states the ruling this slice extends:

> a check that cannot see must not report a pass ... Escalating a blind row to
> error is a deliberate anti-vacuous-green ruling

So this target was never part of the hazard. It is additionally in
`hook_gate_skips` (`scripts/just/check.sh:48`), so it does not run in the
pre-push gate at all and cannot reach a gate pod. Two independent reasons; either
alone is sufficient.

## The disposition

Only the first two rows are both **unlevered** and **in the pre-push gate**, so
only those two could have returned a false green from a credential-less gate
pod. `_gate_context.py` gives them the strict disposition, keyed on the explicit
`LIVESPEC_GATE_CONTEXT` signal that
`ci-runner/k3s/phase2/gates/gate-job-template.yaml` sets and nothing else does:

- **outside** a gate — unchanged: warn, exit 0. A contributor without a forge
  token keeps a runnable gate.
- **inside** a gate — the check FAILS. The conforming responses are to provision
  the executor with the credential the verification requires, or to remove the
  target from the gate recipe. Relocating the verification to the pushing host is
  not one of them: the factory is meant to be self-sufficient, and a local host
  is a dumb driver that should hold no credentials at all.

## The credential the executor needs, and its ceiling

`gates/gate-credentials.yaml` is the non-secret half of that provisioning. Note
what the first row costs: `check-branch-protection-alignment` needs a credential
able to **read branch protection**, which the default Actions `GITHUB_TOKEN`
cannot do (`branch_protection_alignment.py`, the CI-token caveat). `research/003`
section H prescribes projecting "the least-privilege, read-scoped ones as
Secrets", which does not cover that scope — so this is a real cost to be decided
deliberately, not a detail.

A token alone is also **not sufficient**. Both checks resolve the repository from
their clone's `origin` remote — `branch_protection_alignment` matches it against
a github.com-only pattern and skip-passes on anything else — while `research/003`
section E has the gate pod fetch from an in-cluster git daemon whose URL is not
github.com. A pod given the token and nothing else still cannot resolve the repo
it is gating. Whether that is fixed by giving the pod clone a github.com-shaped
`origin` or by changing how those checks name the repository is an
implementation choice; what must not happen is shipping the token and calling the
provisioning done.

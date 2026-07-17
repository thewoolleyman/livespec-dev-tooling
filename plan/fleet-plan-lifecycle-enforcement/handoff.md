# Fleet Plan Lifecycle Enforcement Handoff

**Thread:** `plan/fleet-plan-lifecycle-enforcement/`
**Ledger anchor:** epic `livespec-dev-tooling-scsj5e`

> Status is **derived from the ledger**, never stored in this file. To read it:
> ```bash
> source /data/projects/1password-env-wrapper/with-livespec-env.sh \
>   bd -C /data/projects/livespec-dev-tooling show livespec-dev-tooling-scsj5e
> ```
> (the wrapper injects the tenant password; never echo it).

## Why This Thread Exists

The `rop-sweep-library-checks` work was treated as complete after the
implementation PR merged, but the planning lifecycle was not completed until a
later correction archived the plan thread. A repo-local lint would only prevent
that mistake in `livespec-dev-tooling`; the correct prevention is a fleet-wide
rollout through the shared enforcement package and the existing release/pin-bump
machinery.

This thread owns the fleet rollout. Do not close `livespec-dev-tooling-scsj5e`
until the shared check is released, every manifest fleet member is bumped or has
a filed blocker, and this directory is archived with the epic.

## Ledger Map

Parent epic:

- `livespec-dev-tooling-scsj5e` — `[epic] Fleet-wide plan lifecycle enforcement and rollout`

Child slices, **wired into a strict sequential dependency chain** (verified
2026-07-18 via `bd dep tree`; `bd next` surfaces exactly `i5barz` as ripe, the
rest held `blocked:dependency`):

```
i5barz  ──blocks──▶  w2elyx  ──blocks──▶  qt44u2  ──blocks──▶  zkh4pk
```

- `livespec-dev-tooling-i5barz` — Implement canonical plan-lifecycle enforcement in livespec-dev-tooling *(no deps — ripe)*
- `livespec-dev-tooling-w2elyx` — Dogfood and repair current livespec-dev-tooling plan-thread drift *(depends on i5barz)*
- `livespec-dev-tooling-qt44u2` — Release dev-tooling and fan out the plan-lifecycle check to the fleet *(depends on w2elyx)*
- `livespec-dev-tooling-zkh4pk` — Verify fleet-wide plan-lifecycle enforcement after rollout *(depends on qt44u2)*

The epic is intentionally left `backlog` (it has no assignee; forcing `active`
would violate the `active ⟹ assignee` state invariant). The factory promotes
the epic when the first child is dispatched.

## Execution Order & Why It Is Safe (self-gating analysis)

The naive worry is that wiring a plan-lifecycle check while this repo still
carries the `work-item-state-machine → l2sm(done)` drift would red-block the very
PR that adds the check. It does **not**, because of how the design splits and
where credentials exist:

- **dev-tooling GitHub CI has no ledger/beads credentials.** The matrices export
  only `GITHUB_TOKEN`/App tokens; the 1Password/beads wrapper is host-local
  (`.ai/fleet-and-secrets.md`). So any ledger-aware check **self-skips (green)**
  in CI.
- **The static half stays green** regardless: `work-item-state-machine/handoff.md`
  already declares a concrete `**Ledger anchor:**` line, which is all the static
  check inspects.
- Therefore `i5barz` lands green in CI, and the **dogfood loop is preserved**:
  `w2elyx` runs the ledger-aware half *locally under the wrapper* (creds present),
  which is where it actually detects the `l2sm` drift → repair → re-run green.

This is why the order is **implement → dogfood/repair → release → verify**, not
repair-first. The one caveat: the ledger-aware companion must **never sit in the
default blocking `just check`** in a creds-present environment (operator, Fabro
sandbox), or it would red-block `i5barz` there. The design below enforces that by
gating the companion behind a RUN lever (the established
`check_mutation`/`fleet_conformance` precedent), so it self-skips everywhere by
default and is only armed deliberately.

---

## Slice Runbook 1 — `i5barz`: Implement canonical plan-lifecycle enforcement

**Dispatch through the factory** (see Next Action). Ledger-backed, factory-
eligible; do **not** use the in-session `implement` operation.

### Design of record — two modules

Canonical checks are filesystem-derived (`canonical_checks._discover_slugs`
walks `livespec_dev_tooling/checks/` via `pkgutil.iter_modules`), so dropping a
module in place auto-adds it to the canonical set. Underscore-prefixed modules
are private helpers and excluded.

**Module A — hard STATIC canonical check** (fleet-wide, no creds):
`livespec_dev_tooling/checks/plan_thread_anchor_declared.py`

- Enumerate active handoffs exactly as `handoff_dispatch_routing._active_handoffs`
  does: glob `plan/*/handoff.md`, **excluding `plan/archive/`**
  (`_ARCHIVE_DIR_NAME = "archive"`). Return 0 when `plan/` is absent.
- For each active handoff, require a concrete `**Ledger anchor:**` line naming a
  real epic id. **Fail** when the line is missing, empty, or a placeholder
  (e.g. `<...>`, `TBD`, `<epic-id>`, a bare `epic` with no id). Emit findings as
  structlog JSON to stderr with a `remediation` field; `return 1 if offenders`.
- No ledger read, no creds, no network → runs green everywhere, including every
  credential-less consumer CI. **This is the fleet-wide canonical slug.**

**Module B — ledger-aware COMPANION** (armed-only, creds-gated):
`livespec_dev_tooling/checks/plan_thread_epic_parity.py`

- **Self-skip (exit 0, structured info) unless BOTH:** the RUN lever
  `LIVESPEC_RUN_PLAN_EPIC_PARITY` is truthy **and** the beads credential
  (`BEADS_DOLT_PASSWORD`) is present. This mirrors `check_mutation`
  (`LIVESPEC_RUN_MUTATION`) / `fleet_conformance` (`LIVESPEC_RUN_FLEET_CONFORMANCE`)
  for the RUN lever and `master_ci_green.py` for the credential-absent skip. Being
  in the aggregate but self-skipping is exactly how those checks behave — it keeps
  `aggregate_completeness` happy without ever self-gating a default `just check`.
- **When armed:** for each active thread's anchor epic id, read ledger status via
  the store seam; **fail** if any active (non-archive) thread points at a
  `done`/`closed` epic, or if a `done`/`closed` epic still owns an active
  `plan/<topic>/` dir. Cross-tenant anchors (prose refs like `livespec-…`) are
  **not** treated as this repo's epics — only same-tenant `livespec-dev-tooling-*`
  ids are parity-checked (decisions 41/44/45 in the l2sm thread).
- Do **not** fold the ledger dependency into Module A — a credential-less
  consumer running the canonical slug must never redden.

> Naming: `plan_thread_anchor_declared` / `plan_thread_epic_parity` are the
> design-of-record slugs. Adjust only if a naming/collision check forces it.

### Wiring — every file that must be touched (or `just check` breaks)

Per module (both A and B):

1. `livespec_dev_tooling/checks/<slug>.py` — the module (auto-canonical).
2. `justfile` — add `check-<slug>` to the `check:` aggregate `targets=(…)` array
   (recipe header ~`justfile:151`), **in alphabetical order within the canonical
   block** (`aggregate_completeness` enforces membership + alpha order).
3. `justfile` — a standalone `check-<slug>:` recipe whose body is
   `uv run python -m livespec_dev_tooling.checks.<module>` (model
   `check-handoff-dispatch-routing`, ~`justfile:582`). `canonical_recipe_fidelity`
   requires the literal `python -m livespec_dev_tooling.checks.<module>` substring.
4. `.github/workflows/ci.yml` — add `check-<slug>` to the **`check-metadata`**
   matrix (~`ci.yml:300-339`, next to `check-handoff-dispatch-routing`), **not**
   `check-python`. `ci_matrix_completeness` fails hard
   (`LIVESPEC_FAIL_IF_CI_MATRIX_GAPS_EXIST=true`) if a non-world-gate canonical
   slug is missing from CI. `ci-green.needs` already lists `check-metadata`.
5. `tests/livespec_dev_tooling/checks/test_<slug>.py` — mirror-paired test
   (`tests_mirror_pairing`), driving the in-process `main()` with
   `monkeypatch.chdir` + `capsys` (avoids `tests_no_subprocess_spawn`).
6. **100% line+branch coverage** of each new module (`per_file_coverage`,
   `fail_under=100`).

Do **not** need to touch: `canonical_checks.py` (auto-discovers),
`pbt_coverage_pure_modules` (no-ops here), any SPECIFICATION coverage row (the
enforced string lives in livespec-core, not here), `checks/CLAUDE.md` (exists).

### Module skeleton (matches the repo convention)

```python
"""<slug> — one-line purpose."""
from __future__ import annotations
import sys
from pathlib import Path
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))
import structlog  # noqa: E402
__all__: list[str] = []

def main() -> int:
    log = structlog.get_logger("<slug>")
    cwd = Path.cwd()
    plan_dir = cwd / "plan"
    if not plan_dir.is_dir():
        return 0
    offenders = [...]
    for o in offenders:
        log.error("plan-lifecycle-violation", path=str(o.path), remediation="…")
    return 1 if offenders else 0

if __name__ == "__main__":
    raise SystemExit(main())
```

### TDD (Red-Green-Replay, product `.py`)

Each module is product `.py` → one 2-step single-commit TDD ritual per module
(Red: staged test alone fails on a genuine assertion via the new-module stub
technique; Green amend: real impl). Use `mise exec -- git …`; never `--no-verify`.

### Acceptance (from the work-item)

Red→Green-Replay product `.py` commit(s); tests prove: missing anchor fails,
placeholder anchor fails, archived handoffs are ignored, active→closed-epic drift
is detected by the ledger-aware companion when armed; justfile + CI dogfood
wiring complete. `just check` is green in dev-tooling CI (companion self-skips
there; static passes).

---

## Slice Runbook 2 — `w2elyx`: Dogfood + repair current drift

Unblocks when `i5barz` merges. Factory-eligible.

1. **Dogfood (prove the check bites):** locally, under the wrapper, arm the
   companion and confirm it FAILS on the known drift:
   ```bash
   source /data/projects/1password-env-wrapper/with-livespec-env.sh \
     env LIVESPEC_RUN_PLAN_EPIC_PARITY=1 \
     just check-plan-thread-epic-parity
   ```
   Expect a finding: `plan/work-item-state-machine/` (active) points at
   `livespec-dev-tooling-l2sm`, which is `done`.
2. **Repair — archive the completed thread.** `plan/work-item-state-machine/`'s
   own "Remaining" says to close `l2sm` on merge, and `l2sm` **is** `done`, so the
   thread is complete and must be archived (this is the exact discipline the epic
   enforces):
   ```bash
   git mv plan/work-item-state-machine plan/archive/work-item-state-machine
   ```
   `docs(plan):` subject (exempt from the TDD ritual — no product `.py`), via the
   worktree → PR → merge protocol.
3. **Re-run armed → green.** Then confirm the three enumerations agree the active
   set is `{fleet-plan-lifecycle-enforcement}`:
   - `livespec-orchestrator-beads-fabro:list-plan-threads` (directory-based),
   - `check-handoff-dispatch-routing` (handoff.md-glob),
   - the new `check-plan-thread-anchor-declared` + armed
     `check-plan-thread-epic-parity`.
4. **Evidence:** record the `git mv` merge SHA and a ledger read showing `l2sm`
   `done` with no active thread remaining, in this handoff.

### Acceptance

Active plan-thread list and ledger epic states agree; `plan/archive/` contains
the completed thread; `list_plan_threads` and the new lifecycle checks agree on
the remaining active set.

---

## Slice Runbook 3 — `qt44u2`: Release + fleet fan-out

Unblocks when `w2elyx` merges. The chain is **automatic** on merge to master:

1. **Release (auto).** `i5barz`'s `feat:` moves release-please `0.48.2 → 0.49.0`.
   release-please (App-authored) opens a release PR; `auto-enable-merge` merges it
   on green CI; it tags `v0.49.0` and creates a GitHub Release. App authorship is
   load-bearing — only an App-authored release fires `release: published`.
2. **Fan-out (auto).** `release: published` → `release-dispatch.yml` →
   `reusable-release-dispatch`: a **BLOCKING `fleet-preflight`** runs
   `check-fleet-conformance` against dev-tooling master (a red fleet aborts the
   whole fan-out), then one `repository_dispatch (sibling-released)` fires per
   member. Each member's `bump-pin-from-dispatch` rewrites its pins, runs
   `just check`, and opens a `chore(deps):` auto-merge PR.
3. **Members reached — the 7 fleet siblings** (manifest is
   `/data/projects/livespec/.livespec-fleet-manifest.jsonc` in livespec **core**;
   dev-tooling itself is excluded as publisher):
   - `livespec` (core)
   - `livespec-driver-claude`, `livespec-driver-codex` (driver plugins)
   - `livespec-orchestrator-beads-fabro`, `livespec-orchestrator-git-jsonl` (impl plugins)
   - `livespec-runtime` (library)
   - `livespec-console-beads-fabro` (console)
4. **Manual lever if the auto event is missed.** `release-dispatch.yml` has no
   `workflow_dispatch`; the recovery path is `pin-freshness.yml`
   (`workflow_dispatch` + daily 13:00 UTC) — it opens bump PRs for any stale pin.

### Adopter scope decision (recorded, not deferred silently)

The auto fan-out jq reads only `.fleet`, so the two **adopters**
(`openbrain`, `resume`) are **not** reached. Decision: the automatic rollout is
scoped to the 7 fleet siblings; adopter coverage is tracked explicitly under
`zkh4pk` (file a child blocker if adopters must run the new slug), so "every
member" is never silently overclaimed.

### Acceptance

A released `livespec-dev-tooling` version carries the check; bump-pin PRs are
opened/merged for all 7 fleet siblings; stale/blocked bump PRs are superseded via
pin-freshness or tracked.

---

## Slice Runbook 4 — `zkh4pk`: Verify fleet-wide enforcement

Unblocks when `qt44u2` merges.

1. For **each of the 7 fleet siblings**: confirm the `chore(deps):` bump PR
   merged, the pinned version carries `v0.49.0`+, `just check` is green, the
   canonical aggregate (`aggregate_completeness`) sees the new
   `check-plan-thread-anchor-declared` slug, and `ci_matrix_completeness` includes
   it in that repo's `check-metadata` matrix.
2. **Ledger-aware companion note:** it self-skips in credential-less consumer CI,
   so the fleet-wide *hard* guarantee is the **static** slug. Record where the
   armed `check-plan-thread-epic-parity` sweep runs with creds on an ongoing basis
   (operator-local, Fabro sandbox, or the `livespec-console-beads-fabro` — fleet
   CI cannot, it has no beads creds). If no standing armed home exists yet, file a
   child blocker under this epic rather than claim dynamic enforcement is live.
3. Record per-member evidence (repo, bump PR, CI run, slug-seen) in this handoff.
   File a specific child blocker for any red/blocked member **and** for adopter
   coverage.

### Acceptance

For every fleet sibling, evidence records green CI/conformance with the new
lifecycle enforcement or a specific child blocker. The epic closes only after all
blockers are resolved or deliberately split out.

---

## Open Items / Decisions

- **Adopters (`openbrain`, `resume`)** are outside the automatic fan-out. Tracked
  under `zkh4pk`; decide there whether they must run the canonical slug.
- **Standing armed home for the ledger-aware companion.** Fleet/CI lacks beads
  creds; the dynamic parity invariant is only evaluable where the wrapper is
  present. `zkh4pk` records the ongoing armed context or files a blocker.

## Closure Rule

When the rollout is complete, close `livespec-dev-tooling-scsj5e` in the ledger
(`resolution=completed`, `audit.merge_sha=<final PR sha>`) and move this
directory with:

```text
git mv plan/fleet-plan-lifecycle-enforcement plan/archive/fleet-plan-lifecycle-enforcement
```

## Next Action

Dispatch the first (and only ripe) child through the factory path:

```text
livespec-orchestrator-beads-fabro:drive --action impl:livespec-dev-tooling-i5barz
```

`drive impl:<id>` runs the dispatcher loop **synchronously** for exactly that one
item (`--budget 1 --parallel 1`); `bin/drive.py` self-wraps the tenant
credentials. Do not use the in-session `implement` operation.

**Advancing the chain — one dispatch per slice.** There is no standing
GitHub-Actions dispatcher in this repo (the only crons are `release-park`,
`pin-freshness`, and `fleet-conformance` — none dispatch work-items). So the
chain advances a dispatch at a time: after each slice's PR merges (auto-merge on
a green `ci-green`), `bd next` surfaces the next ripe slice — dispatch it the
same way (`drive impl:<id>`), in order `w2elyx → qt44u2 → zkh4pk`. A standing
dispatcher loop running on the console/Fabro host would pick up each newly-ripe
slice automatically; absent that, an operator dispatches each explicitly. The
`depends_on` edges guarantee `bd next` never surfaces a slice out of order.

# Fleet-wide shell-logic audit — findings, policy, and remediation map

- **Audit completed:** 2026-06-30
- **Scope:** the livespec self-consuming fleet (core, dev-tooling, runtime,
  the two orchestrators, the two drivers, the console) plus the openbrain
  adopter, swept for *substantive logic living in shell or in
  `python -c` / heredoc-Python — i.e. logic outside the
  test + pyright + coverage harness*.
- **Status:** durable consolidated record. Remediation is tracked in the
  ledger under the `shell-logic-hardening` epic
  (`livespec-dev-tooling-9j8`); see [Ledger anchor](#ledger-anchor).
- **Not swept (coverage gap):** the canonical `1password-env-wrapper` repo
  (see [Coverage gap](#coverage-gap)).

## Bottom line (plain language)

The sweep found **no product-logic-in-shell dodge anywhere**: product and
decision logic across the fleet is consistently tested Python / Rust / TS,
and the fleet already polices the `just -> python` boundary
(`check-no-direct-tool-invocation`). The real defect is narrower and
language-agnostic: **untested substantive logic that lives *outside* the
test + pyright + coverage harness** — sometimes in shell scripts, sometimes
in `python -c` / `python - <<EOF` heredocs that happen to be Python but are
not importable, so they evade pyright-strict, ruff, coverage, and the
Result/Railway error-handling discipline.

The maintainer reviewed the audit and **decided on a RULE plus mechanical
GATES, not a blanket shell ban** (2026-06-30). The reasoning: the defect is
untested logic outside the harness, *not* the language — so "force shebang
Python" would not fix heredoc-Python, and some shell legitimately must stay
shell.

## The decided policy

### RULE

Substantive logic — **parsing, transformation, decisions, credential/token
handling, destructive operations** — MUST live in a **tested, type-checked,
importable module (Python or Rust)** inside the test + pyright + coverage
harness, **regardless of how it is invoked**. Shell and `python -c` /
`python - <<EOF` heredocs are limited to **thin glue**: tool invocation,
environment setup, dispatch.

Explicitly: **no substantive logic inside `python3 -c` / `<<PYEOF`
heredocs** — call a tested importable module instead.

### GATES (the enforcement — "fix the gate, not the bypass")

- **(a) Wire `shellcheck` into `just check` + CI fleet-wide.** It is nowhere
  in the fleet today, despite `# shellcheck` directives already present in
  sources. (Ledger: `livespec-dev-tooling-9j8.2`.)
- **(b) Add a `livespec-dev-tooling` logic-in-shell / heredoc ceiling
  check** that flags shell scripts, justfile recipes, CI `run:` blocks, and
  `python -c` / heredoc-Python carrying logic above a threshold. (Ledger:
  `livespec-dev-tooling-9j8.3`.)
- **(c) For FLEET-DISTRIBUTED shell, require behavioral tests**
  (subprocess / bats against tmp git repos) **OR move the decision core into
  tested code.** Record the RULE itself as a fleet discipline. (Ledger:
  `livespec-9sxx`, in core.)

### Rationale (maintainer-endorsed)

The defect is untested logic outside the harness, not the language.
"Force shebang Python" would not fix heredoc-Python; and some shell must
stay shell:

- git hooks that run **before any toolchain** exists,
- container PID-1,
- the pre-toolchain worktree library,
- justfile / lefthook / CI glue.

A blanket ban would mis-target these legitimate cases while doing nothing
about the actual problem (untested decision logic). The RULE targets the
*testability boundary*; the GATES make it mechanical.

## Right-pattern exemplars (the target shape)

These already exist in the fleet and are the shape every remediation should
converge on:

- **`beads-access-guard.sh`** — a thin shim whose only operative line is
  `exec python3 "$(dirname "$0")/beads_access_guard.py"` (plus a fail-open
  `command -v python3` guard and comments). All matching and decision logic
  lives in the paired, importable, unit-tested `beads_access_guard.py`.
  Present at
  `livespec-orchestrator-beads-fabro/.claude/hooks/` and in the shipped
  `livespec/templates/impl-plugin/.claude/hooks/`.
- **The canonical commit-refuse git hook** — minimal *inherent* git-shell
  (it must run before any toolchain), whose installed bytes are
  fingerprint-verified by the tested Python check
  `primary_checkout_commit_refuse_hook_installed`. The shell is irreducible;
  the *verification* is tested code.

## Per-repo verdicts

| Repo | Verdict | Notes |
|---|---|---|
| livespec-console-beads-fabro | **CLEAN** | zero shell logic |
| livespec-runtime | **CLEAN** product surface | product logic is tested |
| livespec-orchestrator-git-jsonl | **CLEAN** product surface | — |
| livespec (core) | **CLEAN** product surface | concerns are peripheral CI shell (export-ci-telemetry) + the rule-as-discipline |
| livespec-orchestrator-beads-fabro | **LOW** | brain is tested Python; only peripheral pockets (reap-e2e, regen_beads_metadata) |
| livespec-driver-codex | **LEAN** (cleanest driver) | — |
| livespec-driver-claude | **LEAN** | hook heredoc-Python is the one pocket |
| **livespec-dev-tooling** | **where logic-in-shell concentrates** | bump-pin rewriters, worktree-lib reap, branch-protection, reusable workflows, check-pre-commit selector |
| openbrain (adopter) | product tested TS/Deno; **operator-shell carries untested logic** | adopter-owned remediation |

No PRODUCT-logic-in-shell dodge anywhere; the `just -> python` boundary is
already policed by `check-no-direct-tool-invocation`.

## Ranked concerns (with file:line refs and ledger ids)

Refs verified present at audit time; line counts match the cited ranges.

1. **[HIGH — port #1] bump-pin-rewrite heredocs** — ledger
   `livespec-dev-tooling-9j8.1` (FIRST READY).
   `livespec-dev-tooling/.github/actions/bump-pin-rewrite/action.yml:118-215`.
   Four `re.compile` + `pattern.subn` pin-rewriters
   (`livespec_jsonc_compat_pinned`, `pyproject_toml_uv_sources`,
   `vendor_jsonc`, `github_workflow_uses_ref`) embedded as `python - <<PYEOF`
   heredocs inside a bash `case`. Only static-text-tested, while the
   *detection* sibling
   `livespec_dev_tooling/cross_repo/pin_autodiscovery.py` is fully unit +
   mutation tested. Strongest "resembles circumvention" instance. **Port the
   rewrite half into a tested `pin_rewrite` module called via `python -m`.**

2. **[port #2 — fleet-wide leverage] export-ci-telemetry.sh** — ledger
   `livespec-gnjb` (core tenant, READY).
   `livespec/.github/scripts/export-ci-telemetry.sh:34-121` — a ~90-100 LOC
   OTLP / jq / HTTP span builder + pass/fail decision, untested. Shipped via
   `livespec/templates/impl-plugin/.github/scripts/export-ci-telemetry.sh`,
   byte-identical in livespec-runtime, livespec-orchestrator-git-jsonl,
   livespec-orchestrator-beads-fabro, and the drivers. **Port to a tested
   Python module in CORE + re-stamp the impl-plugin template -> fixes the
   whole fleet at once.**

3. **[MED-HIGH — destructive] worktree-lib reap decision** — ledger
   `livespec-dev-tooling-9j8.4`.
   `livespec-dev-tooling/livespec_dev_tooling/worktree_pack/worktree-lib.sh:223-383`
   (+115-215) — ~300 LOC `git worktree list --porcelain` parser state
   machine + reap keep/remove/FORCE decision. The `--force` path runs
   `git worktree remove --force` + `branch -D`, **discarding uncommitted
   work**. Shipped fleet-wide, verified only for byte-identity; behavior
   never tested. Legitimately shell (runs before any toolchain) does **not**
   mean untested. **Add behavioral tests OR move the decision core to tested
   code.**

4. **[MED] branch-protection.sh gh-API orchestration** — ledger
   `livespec-dev-tooling-9j8.5`.
   `livespec-dev-tooling/livespec_dev_tooling/worktree_pack/branch-protection.sh:80-137`
   — ~140 LOC: origin-URL `sed` parse, HTTP-status `grep` branching,
   protection-shape asserts; untested in consumers.

5. **[MED] driver-claude hook heredoc-Python** — ledger
   `livespec-driver-claude-hxn` (driver-claude tenant).
   `livespec-driver-claude/.claude-plugin/hooks/block-auto-memory.sh:47-158`
   and `warn-plan-persistence.sh:31-165` — ~100-110 LOC of genuine Python
   (JSONC stripper + block decision; transcript turn-window parser +
   threshold counting) inside `python3 -c` heredocs. Subprocess-tested, but
   evades pyright-strict / ruff / coverage / Result-ROP because not
   importable. **Convert to `exec python3 "$CLAUDE_PLUGIN_ROOT/scripts/<mod>.py"`
   over a tested importable module** (the `beads-access-guard.sh` shim shape).

6. **[MED] dev-tooling reusable workflows** — ledger
   `livespec-dev-tooling-9j8.6`.
   `reusable-pin-freshness.yml:124-168` (awk ordinal-distance staleness
   compare) and `reusable-release-dispatch.yml:101-134,204-237` (manifest
   `curl` + comment-strip + `.fleet // .members` array build; dispatch
   payload + `gh api` + awk http-status soft-fail branching).

7. **[LOW] check-pre-commit gate-selector prefix drift** — ledger
   `livespec-dev-tooling-9j8.7`.
   Fleet-wide justfile gate-selector (e.g. `livespec/justfile:448-496`, with
   runtime / git-jsonl / dev-tooling analogues) re-encodes the Python
   `_IMPL_PREFIXES` constant in bash (drift risk). Only SELECTS which local
   gate runs; fully backstopped by the Python `red_green_replay` at
   commit-msg + pre-push + CI. **Fix = derive the prefixes from the Python
   source of truth rather than re-encode.**

8. **[MED/LOW — repo-specific] orchestrator-image shell** — ledger
   `bd-ib-k5p` (orchestrator-beads-fabro tenant).
   `livespec-orchestrator-beads-fabro/orchestrator-image/reap-e2e-repos.sh:151-247`
   (destructive age-gated repo-deletion decision + retry/error-classify,
   untested) and `real-work-dispatch.sh:374-429` (`regen_beads_metadata`:
   hand-rolled awk YAML parser + bd embedded/server-mode classification).

9. **[adopter] openbrain operator-shell** — ledger `ob-vc7y` (openbrain
   tenant, **adopter-owned**).
   `openbrain/scripts/verify-openbrain-env.sh:231-265` (live OAuth
   refresh -> access-token exchange + People-API HTTP branching, runs on a
   pre-push gate + CI) plus `scripts/lib/pnpm-safety-gates.sh`,
   `scripts/honeycomb-mcp.sh`, `scripts/release-android.sh` semver math.
   openbrain is an external adopter — filed in its tenant, marked
   adopter-owned, prioritized by openbrain.

10. **[GATES — enforcement deliverables]** — ledger
    `livespec-dev-tooling-9j8.2` (shellcheck fleet-wide),
    `livespec-dev-tooling-9j8.3` (logic-in-shell / heredoc ceiling check),
    `livespec-9sxx` (record the RULE as a fleet discipline in core
    `.ai/agent-disciplines.md` and/or the relevant `SPECIFICATION` contract).

11. **[coverage gap] 1password-env-wrapper not swept** — ledger
    `livespec-dev-tooling-9j8.8`. See [Coverage gap](#coverage-gap).

## Ledger anchor

Epic **`livespec-dev-tooling-9j8`** ("[epic] Fleet-wide shell-logic
hardening") anchors the dev-tooling-owned work. Cross-repo concerns are
filed as child work-items in their OWN tenants with a **prose
cross-reference** to this epic — never a typed cross-tenant `depends_on`
(it would dangle across independent stores).

| Concern | Ledger id | Tenant | Link |
|---|---|---|---|
| #1 bump-pin-rewrite port (FIRST READY) | `livespec-dev-tooling-9j8.1` | livespec-dev-tooling | child of epic |
| #10a shellcheck gate | `livespec-dev-tooling-9j8.2` | livespec-dev-tooling | child of epic |
| #10b logic-in-shell ceiling check | `livespec-dev-tooling-9j8.3` | livespec-dev-tooling | child of epic |
| #3 worktree-lib reap (destructive) | `livespec-dev-tooling-9j8.4` | livespec-dev-tooling | child of epic |
| #4 branch-protection.sh | `livespec-dev-tooling-9j8.5` | livespec-dev-tooling | child of epic |
| #6 reusable workflows | `livespec-dev-tooling-9j8.6` | livespec-dev-tooling | child of epic |
| #7 check-pre-commit selector drift | `livespec-dev-tooling-9j8.7` | livespec-dev-tooling | child of epic |
| #11 1password-env-wrapper audit | `livespec-dev-tooling-9j8.8` | livespec-dev-tooling | child of epic |
| #2 export-ci-telemetry port (FIRST READY) | `livespec-gnjb` | livespec (core) | prose ref |
| #10c record the RULE as discipline | `livespec-9sxx` | livespec (core) | prose ref |
| #5 driver-claude hook heredocs | `livespec-driver-claude-hxn` | livespec-driver-claude | prose ref |
| #8 orchestrator-image shell | `bd-ib-k5p` | livespec-orchestrator-beads-fabro | prose ref |
| #9 openbrain operator-shell (adopter-owned) | `ob-vc7y` | openbrain | prose ref |

The two **ports** — `livespec-dev-tooling-9j8.1` (bump-pin) and
`livespec-gnjb` (export-ci-telemetry) — are marked the FIRST READY children.
All items were filed via `bd create` (the capture-work-item fallback) and
**need grooming** into final ready / dependency-layered slices.

## Evidence the gate matters

The live "use shell to sidestep conformance" *instinct* — not a finding in
existing code, but a behavior observed during work — appeared this session
in an orchestrator App-token-mint attempt (work-item `bd-ib-gsl`): the
reflex to drop into shell to avoid the harness's conformance checks. It was
caught and redirected to tested Python. This is direct evidence that the
RULE needs a mechanical GATE, not just a written convention — the pull
toward untested shell is active, not hypothetical.

## Coverage gap

The canonical **`1password-env-wrapper`** repo — the source of the
secret-handling `with-<project>-env.sh` re-exec wrappers used fleet-wide —
was **not swept** by this audit. Because it handles credentials, it is
exactly the kind of repo the RULE most cares about. A follow-up audit of it
under the same RULE is filed as `livespec-dev-tooling-9j8.8` (anchored in
dev-tooling because `1password-env-wrapper` carries no beads tenant).

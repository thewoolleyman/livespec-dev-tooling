# Triage batch 6 — the shell-logic-hardening orphans, 2026-09-08

**Status: PROPOSAL.** The one close and one rescope below await the maintainer's
ruling, per the batch-1 precedent. What was done unilaterally is the reading:
all seven items are labelled `intake:triaged` and each carries its finding as a
comment.

Session: `plan-session:dev-tooling-backlog-drain-2026-09-08-resume-0908g`.
Untriaged open snapshot items: **107 before this batch, 100 after** (119 at the
start of the session).

## Why this cluster is this plan's to decide, and batch 5's was not

Batch 5 *deferred* the `8o8e` children because a live plan
(`plan/rop-railway-enforcement`) owns them and had already dispositioned them.

This cluster is the opposite case, and that is the batch's first finding:

> **`plan/shell-logic-hardening` is ARCHIVED and its epic `9j8` is CLOSED — yet
> six children are still open.**

The plan directory is now `plan/archive/shell-logic-hardening/` (its durable
`research/findings.md` survives there). A plan's archive gate is supposed to
refuse while any child is undisposed — that is exactly the gate
`rop-railway-enforcement` is currently stuck behind. Here it did not hold, so
**nothing owns these six today**. That is why this drive decides them rather
than deferring.

A second property they share: **every one carries an empty `acceptance_criteria`
field**, so the engine would refuse each as dispatched. That is the same
condition that made `675skf` and `py9` look ready and not be.

## `9j8.2` — premise falsified, propose CLOSE

The item asks to wire shellcheck into `just check` and CI, on the premise that
"shellcheck is nowhere in the fleet today". Measured against this repo at master,
that premise no longer holds:

- `just check-shell-quality` exists, backed by
  `livespec_dev_tooling/checks/shell_quality.py`, which calls
  `run_shellcheck(repo_root=...)` and converts each result to a `Finding`.
- It is in CI: `.github/workflows/ci.yml:621`.
- **It cannot pass vacuously.** The module has an explicit
  `_finding_for_shellcheck_unavailable` path emitting
  `reason="shellcheck-unavailable"`, so a missing binary is *reported*, not
  skipped. That is precisely the property the item's own
  "fix-the-gate-not-the-bypass" framing demands.
- shellcheck is pinned in the toolchain (mise, 0.11.0).

**Stated rather than assumed:** this measures `livespec-dev-tooling` only, while
the item says *fleet-wide*. If the maintainer reads the scope as all nine repos,
the correct disposition is to close the dev-tooling half and refer the fan-out —
the shape batch 5 proposed for the `8o8e` arming children.

## `9j8.3` — partially landed, propose RESCOPE

The item wants one check over four surfaces. Two are covered, two are not.

**Covered:**

- *Justfile recipes* — `_shell_quality_recipes.py` reads the `just --dump` JSON
  and reports a recipe for just-interpolation, for parameters without
  `positional-arguments`, for omitting errexit without documented rationale, and
  for being a **non-thin recipe** (a shebang body, more than one command, or
  shell syntax belonging in a script). That is *stricter* than the threshold the
  item asked for — a structural rule rather than a size ceiling.
- *Shell scripts* — linted by shellcheck via the same check. The honest limit:
  shellcheck finds defects, it does not measure "substantive logic", so this is
  coverage of correctness, not of the logic-placement rule.

**Not covered:**

- *CI `run:` blocks* — nothing reads `.github/workflows/*.yml` `run:` bodies for
  logic content.
- *`python -c` and heredoc-Python* — grepping the whole `checks/` tree for
  `heredoc`, `python -c` and `python3 -c` returns **zero hits**.

That second gap matters more than its size suggests. It is the archived audit's
*central* finding: Python that "happens to be Python but is not importable, so it
evades pyright-strict, ruff, coverage, and the Result/Railway discipline". **The
rule is enforced where it is cheapest and unenforced exactly where the audit said
the real dodge lives.** Rescoping keeps that visible instead of letting a partial
landing read as done.

## `9j8.4`–`.7` — still live, propose KEEP

None is falsified. All are work in *this* repository's tree, so unlike batch 5's
referrals they are reachable by this plan's factory path.

| item | subject | severity as this drive reads it |
|---|---|---|
| `.4` | `worktree-lib.sh` reap keep/remove/FORCE decision | **HIGH** — the `--force` path runs `git worktree remove --force` + `branch -D`, discarding uncommitted work; shipped fleet-wide, verified only for byte-identity, behaviour never tested |
| `.5` | `branch-protection.sh` gh-API orchestration | MED — a wrong protection-shape assert fails toward believing a branch is protected when it is not |
| `.6` | `run:` logic in `reusable-pin-freshness.yml` + `reusable-release-dispatch.yml` | MED — **on the critical path**: `zm5cbp` declares a blocks dependency on it |
| `.7` | `check-pre-commit` selector re-encoding `_IMPL_PREFIXES` in bash | LOW — selects only which local gate runs, fully backstopped by the Python `red_green_replay` at commit-msg, pre-push and CI |

They are **not** blocked by the two gate children: the gates would *detect* this
code, while these items are the remediation itself.

The one thing between each and a dispatch is the empty `acceptance_criteria`
field. Each description already carries a `DO:` directive in positive-observation
form, so this is nearer the transcription case than the authoring case — and
either way it is established practice on this plan, not a maintainer cut.

## `9j8.8` — propose KEEP HERE, explicitly do not refer out

It looks like batch 5's referral shape and is not. Its own text records why:
**`1password-env-wrapper` has no beads tenant**, so there is nowhere to refer it
to. Referring it out would delete it, not move it.

It is the archived audit's declared **coverage gap** — `findings.md` lists that
repo under "Not swept". That repo is the source of the `with-NAME-env.sh`
re-exec wrappers, i.e. the fleet's *credential-handling* shell, and it is the one
body of shell the sweep never read. An unswept credential wrapper is the
highest-consequence instance of the defect class the whole plan existed to close.

It is also demonstrably live rather than historical:
`/usr/local/bin/with-livespec-env.sh` is what every ledger read in this session
went through, and this repo's `AGENTS.md` documents that a bare `bd` fails with
`Error 1045` without it.

**One question it raises worth settling once:** an audit is a *read*, so it may be
satisfiable by pointing a run at a path rather than needing a tenant. That answer
decides whether audit-shaped items can ever be dispatched here at all.

## What this batch asks for

1. Ratify or reject the `9j8.2` close (and say whether "fleet-wide" means refer
   the fan-out).
2. Ratify or reject the `9j8.3` rescope to CI `run:` blocks and heredoc-Python.

Neither holds the factory. Both are cheap to answer and each removes an item that
would otherwise be re-read every triage pass.

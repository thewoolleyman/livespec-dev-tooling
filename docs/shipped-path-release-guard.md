# The shipped-path release guard

A change typed `docs(...)` — or typed anything else the repository does not cut a
release on — to a path a plugin SHIPS reaches ZERO running seats. Nothing cuts a
release, so no pin moves, and `just ensure-plugins` reports "already current"
because that command compares PINS, not served bytes. The edited file is correct
in `master` and stale everywhere it is actually read.

The guard closes that gap. It is deliberately split in two, so that one rule has
exactly one implementation:

- `livespec_dev_tooling/shipped_path_release_guard_core.py` — the PURE decision.
  It takes the commit subject and body, the changed paths, the repo's releasing
  types, the shipped prefixes and an override flag, and answers whether the
  change edits shipped bytes no release will carry. No git, no filesystem, no
  environment.
- `livespec_dev_tooling/shipped_path_release_guard_check.py` — the RUNNABLE
  check. It resolves every one of those inputs from the real repository and then
  delegates the answer to the core. It decides nothing itself.

## Running it

```bash
just check-shipped-path-release-guard [MESSAGE_FILE]
```

The check has TWO MODES, and the presence of `MESSAGE_FILE` selects between them.

**Commit-msg mode — one argument.** `MESSAGE_FILE` is the pending commit's
message file, the argument git's `commit-msg` hook passes as `$1`. The changed
paths come from `git diff --cached --name-only`, run in the current working
directory. This mode judges the one commit being written.

It is a commit-msg-scoped gate rather than a pre-commit one for a structural
reason: both the commit TYPE and the override marker live in the commit message,
and at pre-commit time that message does not exist yet.

**Range mode — no argument.** The check judges every non-merge commit in
`origin/master..HEAD`, each against its OWN message and its OWN changed paths.
This is what `just check`, pre-push and CI run, and it is the branch-level gate
behind the per-commit hook — which a rebase, a squash or a history rewrite can
bypass.

Range mode is why the no-argument invocation no longer falls back to reading
`<git-dir>/COMMIT_EDITMSG`. The aggregate runs with no pending commit: argv is
empty and the staged diff is empty, so that fallback judged the LAST commit's
already-decided message against no changed paths and therefore COULD NOT FAIL.
An aggregate member that cannot fail is the defect the enforcement suite exists
to remove.

An unresolvable `origin/master` REFUSES rather than passes: a shallow clone
yields an empty commit list, which is indistinguishable from a clean branch, so
treating it as clean would fail open. Fetch the base ref, or check out with full
history in CI.

Exit `0` when there is no violation; exit `1` on a violation, when the message
file cannot be read, or when the range base cannot be resolved.

## The override marker

The guard must force an EXPLICIT decision, not forbid the edit. There is a
legitimate case — a genuine documentation edit to a shipped `.md` that really
does warrant no release — and a guard that only refuses would either block it
outright or teach everyone to reach for a bypass flag.

The marker is a commit-message trailer:

```text
Shipped-Path-Release-Waived: <why this edit warrants no release>
```

Spelling rules, all load-bearing:

- The trailer must start at the beginning of its own line.
- The reason after the colon must be NON-EMPTY. A bare
  `Shipped-Path-Release-Waived:` is not an override — the whole point of the
  marker is that a human wrote down why, so a valueless trailer records nothing.
- It is matched anywhere in the message, subject line included, so it survives
  `git commit --amend` and rebases that reflow the body.

The alternative to an override is simply to retype the commit to a type this
repository releases on — which is usually the right answer, because bytes that
ship generally SHOULD reach seats.

## Where the per-repo inputs come from

Neither input is a fleet constant. Both are resolved from the repository under
inspection, and the check logs which source each value came from on every run.

**Releasing types** are read from the repository's release-please config —
`release-please-config.json`, or `.release-please-config.json` — taking the
`changelog-sections` entries that are NOT `hidden: true`. When the repository
declares no `changelog-sections`, release-please's own defaults apply
(`feat`, `feature`, `fix`, `perf`, `revert`).

This is per-repo in BOTH directions and hardcoding either answer is a defect.
release-please hides `refactor` by DEFAULT, so a repository declaring no
`changelog-sections` does not release on `refactor` — while livespec, which
declares `{"type": "refactor", "section": "Refactoring", "hidden": false}`, does.
A single constant could only ever be right for one of those two repositories.
livespec's release history is the evidence: `v0.28.2..v0.28.3` held 36 commits —
5 `refactor`, 5 `chore`, 26 `docs`, zero `feat`, zero `fix`, zero breaking
markers — and `v0.28.3` was cut.

A breaking marker always releases regardless of the set: a `!` on the type, or a
`BREAKING CHANGE:` / `BREAKING-CHANGE:` footer.

**Shipped prefixes** are DERIVED, not declared: every directory named
`.claude-plugin` that carries a `plugin.json` or a `marketplace.json` manifest,
searched at the repository root and one level below it. Those are the two layouts
the fleet uses. For livespec the derivation yields `.claude-plugin/`. A
repository with no such manifest ships no plugin bytes, the derived set is empty,
and the guard cannot fire — which is the honest answer rather than a silent one:
the check logs the empty derivation and its source like any other.

## Wiring

The guard is ARMED in livespec-dev-tooling (work-item
`livespec-dev-tooling-sxdz`), in both modes:

- `lefthook.yml`'s `commit-msg` hook runs `02-shipped-path-release-guard` —
  `just check-shipped-path-release-guard {1}` — immediately after
  `01-red-green-replay`. It delegates to `just` rather than shelling out to
  `python`/`uv`, per the spec's lefthook-must-delegate-to-just rule.
- The `just check` aggregate (and `check-targets.txt`, its other reader) wires
  `check-shipped-path-release-guard`, which runs in range mode.

`check-shipped-path-release-guard` is NOT a canonical-aggregate slug: its module
lives at `livespec_dev_tooling/shipped_path_release_guard_check.py` rather than
under `livespec_dev_tooling/checks/`, so `canonical_checks.py`'s filesystem walk
does not discover it. It is wired in the repo-private block below the canonical
set, where `check-aggregate-completeness` requires extras to sit.

**In livespec-dev-tooling itself the guard is correctly INERT.** This repository
carries no `.claude-plugin/` manifest at its root or one level below, so its
derived shipped set is empty and no commit here can violate. That is the honest
answer rather than a silent one — every run logs the empty derivation and its
source string. The guard is armed here for the consumers whose derived sets are
not empty, and arming it in an inert repository is a deliberate no-op rather than
an untested green.

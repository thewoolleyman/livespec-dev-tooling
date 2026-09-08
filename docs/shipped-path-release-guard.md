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
python -m livespec_dev_tooling.shipped_path_release_guard_check [MESSAGE_FILE]
```

`MESSAGE_FILE` is the pending commit's message file. It is the argument git's
`commit-msg` hook passes as `$1`; omit it and the check falls back to
`<git-dir>/COMMIT_EDITMSG`. The changed paths come from
`git diff --cached --name-only`, run in the current working directory.

It is a commit-msg-scoped gate rather than a pre-commit one for a structural
reason: both the commit TYPE and the override marker live in the commit message,
and at pre-commit time that message does not exist yet.

Exit `0` when there is no violation; exit `1` on a violation, or when the message
file cannot be read.

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

Wiring the guard into `lefthook.yml`'s `commit-msg` hook and into the
`just check` aggregate is a SEPARATE change (work-item
`livespec-dev-tooling-sxdz`). Until it lands, the check is runnable and tested
but not armed, so no repository is gated on it.

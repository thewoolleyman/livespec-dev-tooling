# Agent instructions

## Codex dogfooding (OpenAI Codex CLI/TUI)

This repo's `/livespec:*` and orchestrator surfaces can be dogfooded from
OpenAI Codex CLI/TUI, not just Claude Code. Unlike the Claude path (plugins
enabled PER PROJECT via a committed `.claude/settings.json`), Codex plugin
enablement is **HOST-WIDE**: each registration persists in `~/.codex/config.toml`
and applies to every project on the host. Codex offers no project-scoped plugin
enablement, so there is no committed-settings analogue for the Codex path.

Install the three fleet plugins host-wide: livespec CORE (the artifact carrier
that ships the spec-side prose and wrappers), the `livespec-driver-codex` Codex
Driver (which supplies the `/livespec:*` operation surface over core's prose),
and the selected orchestrator plugin:

```bash
# livespec CORE (spec-side prose + wrappers; no skills of its own):
codex plugin marketplace add thewoolleyman/livespec
codex plugin add livespec@livespec

# The Codex Driver (supplies the spec-side /livespec:* operation surface):
codex plugin marketplace add thewoolleyman/livespec-driver-codex
codex plugin add livespec@livespec-driver-codex

# The selected orchestrator plugin (ships its own Codex skills):
codex plugin marketplace add thewoolleyman/livespec-orchestrator-beads-fabro
codex plugin add livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro
```

Once installed, Codex operations are driven via `codex exec` and NAME-selected as
`<plugin>:<op>` (for example, `livespec:next`,
`livespec-orchestrator-beads-fabro:list-work-items`) rather than as
`/`-prefixed slash commands. The distributed Drivers resolve their prose at
runtime; no `AGENTS.md` skill-to-prose mapping is required. See
`livespec/SPECIFICATION/contracts.md` §"Plugin distribution" and
`livespec/SPECIFICATION/non-functional-requirements.md` §"Codex dogfooding
contracts" for the authoritative install and resolution contracts.

The Codex TUI picker displays skills by short name with the plugin as context.
In `/skills` → `List skills` (or the `@` picker), search the operation name,
for example `orchestrate`; the row renders as
`orchestrate (livespec-orchestrator-beads-fabro)` with kind `Skill`. The
colon-qualified form `livespec-orchestrator-beads-fabro:orchestrate` is still
valid for prompt / `codex exec` name selection and model-visible skill
references, but it is not the picker row operators should expect.

## Repository mutation protocol

Every repo change uses a worktree → PR → merge → cleanup path. Treat
leaving dirty state, committing on the primary checkout, or asking the
user whether to commit as failures of the workflow, not as acceptable
stopping points.

1. Confirm the primary checkout before editing:

   ```bash
   git -C /data/projects/livespec-dev-tooling config --get livespec.primaryPath
   git -C /data/projects/livespec-dev-tooling status --short --branch
   ```

2. If the change will modify tracked files, create a dedicated worktree
   from the primary checkout's `master` and do all edits there. Every
   fleet worktree lives under the per-user root `~/.worktrees/<repo>/<branch>`
   (never a peer of the clones in `/data/projects`); `just bootstrap`
   registers `~/.worktrees` in mise's `trusted_config_paths`, so a
   freshly created worktree's `.mise.toml` auto-trusts and the first
   `mise exec` inside it never stops on the "config not trusted" prompt:

   ```bash
   mise exec -- git -C /data/projects/livespec-dev-tooling worktree add -b <branch> "$HOME/.worktrees/livespec-dev-tooling/<branch>" master
   ```

3. Use `mise exec -- git commit ...` and `mise exec -- git push ...` so
   the mise-managed lefthook hooks actually run. Never pass
   `--no-verify`, and never set `LEFTHOOK=0`, `LEFTHOOK=false`,
   `LEFTHOOK=off`, or `LEFTHOOK=no`; those disable the same load-bearing
   hook surface. If a hook fails, fix the cause or halt with the failure.
4. Open a PR, wait for required checks, and merge through the PR using
   the repo's rebase-merge discipline.
5. After merge, refresh `/data/projects/livespec-dev-tooling` to
   `origin/master`, remove the feature worktree, delete the local
   branch, and verify the primary checkout is clean on `master`.

Do not leave orphaned worktrees. If a session must stop before cleanup,
record the active worktree path, branch, PR, validation state, and next
action in the relevant handoff document.

## Red-Green-Replay commit protocol

Product `.py` changes are committed via a 2-step single-commit TDD ritual,
enforced by the `red_green_replay` commit-refuse hook (it inspects the staged
tree and writes `TDD-*` trailers). The final result is ONE commit carrying the
test, the impl, and both trailer sets.

1. **Red commit.** Stage the test file ALONE — no impl — and commit with a
   `fix:`/`feat:` subject. The hook runs pytest on the staged tree; the staged
   test MUST fail on pytest (non-zero exit). An `ImportError` or a collection
   error counts as a failure to the hook, BUT you SHOULD prefer a genuine
   assertion failure so Red proves the behavior is actually unimplemented
   rather than merely unimportable — see the new-module stub technique below.
   It records `TDD-Red-*` trailers (test path, failure reason, test-file
   checksum, output checksum, captured-at).
   - Gotcha: the impl must be UNMODIFIED on disk at the Red commit, because the
     hook's pytest reads the on-disk module. If the impl already carries the
     change the test passes, and the hook rejects with `test-passed-at-red`.
2. **Green amend.** Stage the impl and run `git commit --amend`. The hook sees
   the `TDD-Red-*` trailers + the staged impl, re-runs the SAME test (now
   passing), and records `TDD-Green-*` trailers. The test file bytes MUST be
   byte-identical across the Red→Green pair; to change the test, author a fresh
   Red commit.

### New-module stub technique (avoiding false reds)

When the impl module under test does NOT exist yet, the natural Red would be an
`ImportError` or a collection error rather than an assertion failure. The hook
accepts that as a failing Red, but it does not prove the behavior is
unimplemented — only that the module is unimportable. To make Red fail on a
genuine assertion instead:

1. At Red time, create the impl module as a minimal **stub** on disk — enough
   that the test imports and runs, but its assertion FAILS (e.g. a function
   that returns a wrong/sentinel value, or raises `NotImplementedError` only
   when that still yields an assertion failure rather than a collection error).
2. The stub must NOT make the test pass — a passing test at Red trips the
   hook's `test-passed-at-red` gate.
3. Then the **Green amend** replaces the stub with the real implementation that
   makes the assertion pass.

This keeps Red honest: it proves the behavior is unimplemented, not merely that
the module is missing.

**Exempt:** changesets with no product `.py` (docs, spec, work-items, shell,
config) use `chore(...)` / `docs(...)` / `chore(spec):` subjects and skip the
ritual entirely. Always use `mise exec -- git ...` so the hooks fire; never
pass `--no-verify`.

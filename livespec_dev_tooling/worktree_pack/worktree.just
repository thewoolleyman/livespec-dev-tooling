# worktree.just — canonical worktree-lifecycle recipe stanzas (single source).
#
# This file is the SINGLE canonical source of the four `just worktree-*`
# lifecycle recipes. It is installed into a consumer repo's
# `dev-tooling/worktree.just` by `just install-worktree-pack` (the
# from-package installer `livespec_dev_tooling.install_worktree_pack`) and
# `import`ed from the consumer's root justfile — so consumers no longer copy
# the recipe text into their own justfile.
#
# DO NOT EDIT the installed copy by hand: the
# `primary-checkout-commit-refuse-hook-installed` check byte-verifies it
# against the package source. Change the canonical source in the
# `livespec-dev-tooling` package and re-run `just install-worktree-pack` to
# re-sync every consumer.
#
# The recipes are ecosystem-neutral one-line pass-throughs onto the worktree
# lifecycle core `./dev-tooling/worktree-lib.sh`. The `import`ing root
# justfile runs with the repository root as the working directory, so that
# relative path resolves; the core carries all the logic, the recipes stay
# logic-free.
#
# ARGUMENTS RIDE `[positional-arguments]` + `"$@"`, NEVER `{{...}}`. `just`
# interpolation splices a parameter into the recipe text BEFORE the shell sees
# it, so a value containing whitespace or a shell metacharacter re-parses as
# extra words; `"$@"` passes each argument through as one word. That is also
# what `check-shell-quality` enforces on every recipe in the importing repo's
# resolved justfile — and this file's recipes are part of that resolution, so a
# `{{...}}` here turned every consumer's own justfile red the moment the pack
# was installed.

# Branch a fresh isolated worktree from the default branch under
# ~/.worktrees/<repo>/<branch> and hydrate it (ecosystem profile).
[positional-arguments]
worktree-create branch base_ref="":
    ./dev-tooling/worktree-lib.sh create "$@"

# Run the ecosystem-profile hydrate hook in the current worktree.
worktree-hydrate:
    ./dev-tooling/worktree-lib.sh hydrate

# Rebase the current worktree branch onto the latest base, then report the
# next landing step (the core never auto-pushes).
[positional-arguments]
worktree-land base_ref="":
    ./dev-tooling/worktree-lib.sh land "$@"

# Report (dry-run) or remove (--execute) stale/orphaned worktrees. Pass
# extra args through, e.g. `just worktree-reap --execute`.
[positional-arguments]
worktree-reap *args:
    ./dev-tooling/worktree-lib.sh reap "$@"

# ---------------------------------------------------------------
# Detached gate runner (work-item livespec-dev-tooling-yilyxr.7).
# Runs a gate command in its own session that outlives any harness
# tool-call ceiling and reports a durable verdict; `start` also
# preflights this pack itself, so a fresh worktree that skipped
# `just bootstrap` self-heals in seconds instead of burning a full
# aggregate run to fail on the pack check. A run that does not
# finish reports DIED_WITHOUT_VERDICT — it can never read as a pass.
# ---------------------------------------------------------------

# Launch a gate command detached; prints the run id and returns fast.
[positional-arguments]
gate-start *args:
    ./dev-tooling/gate-run.sh start "$@"

# Block until a run reaches a terminal state; exits with its verdict.
[positional-arguments]
gate-wait *args:
    ./dev-tooling/gate-run.sh wait "$@"

# One-shot verdict for a run (or the latest); never blocks.
[positional-arguments]
gate-status *args:
    ./dev-tooling/gate-run.sh status "$@"

# List recent gate runs, newest last.
gate-list:
    ./dev-tooling/gate-run.sh list

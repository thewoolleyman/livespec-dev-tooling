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

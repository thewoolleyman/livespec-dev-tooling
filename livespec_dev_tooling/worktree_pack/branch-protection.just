# branch-protection.just — canonical server-side branch-protection recipe stanzas (single source).
#
# This file is the SINGLE canonical source of the two server-side
# branch-protection recipes (`protect-default-branch`,
# `check-branch-protection`). It is installed into a consumer repo's
# `dev-tooling/branch-protection.just` by `just install-worktree-pack` (the
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
# The recipes are ecosystem-neutral one-line pass-throughs onto the
# server-side branch-protection mirror `./dev-tooling/branch-protection.sh`.
# The `import`ing root justfile runs with the repository root as the working
# directory, so that relative path resolves; the script carries all the logic,
# the recipes stay logic-free.

# Establish baseline GitHub branch protection on the default branch (requires an
# admin-scoped gh token). Idempotent + non-weakening; FORCE=1 resets to baseline.
protect-default-branch:
    ./dev-tooling/branch-protection.sh apply

# Verify the default branch is protected (the server-side tripwire). Fail-closed
# but capability-aware; tune via LIVESPEC_BRANCH_PROTECTION_CHECK=fail|warn|skip.
check-branch-protection:
    ./dev-tooling/branch-protection.sh check

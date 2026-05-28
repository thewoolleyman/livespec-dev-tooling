#!/bin/sh
# livespec commit-refuse hook — refuses commits/pushes at the primary checkout.
#
# Per livespec/SPECIFICATION/non-functional-requirements.md
# §"Primary-checkout commit-refuse hook": every livespec-governed
# primary checkout MUST install this hook body at
# .git/hooks/pre-commit AND .git/hooks/pre-push. The hook is a
# silent no-op at secondary worktrees because
# `git rev-parse --show-toplevel` returns the WORKTREE's path
# (not the primary's) when invoked inside a worktree, so the
# toplevel comparison fails and the hook delegates straight to
# lefthook.
#
# The recognized canonical fingerprint (per the doctor invariant
# at livespec/SPECIFICATION/contracts.md
# §"`primary-checkout-commit-refuse-hook-installed`") consists of
# the marker comment string `# livespec commit-refuse hook` plus
# the `git rev-parse --show-toplevel` invocation plus an `exit 1`
# branch. The fingerprint match is substring-based and tolerant
# of portable-shell rewrites.
#
# After the refuse-at-primary check passes (i.e. we're at a
# worktree), delegate to lefthook so the existing pre-commit /
# pre-push gates (00-lint-autofix-staged, 01-commit-pairs-source-
# and-test, 02-check-pre-commit, etc.) continue to fire. The
# hook-name is derived from the basename of $0 so the same script
# can serve both pre-commit and pre-push without per-hook copies.

primary_path="$(git config --get livespec.primaryPath || true)"
toplevel="$(git rev-parse --show-toplevel)"
if [ -n "$primary_path" ] && [ "$toplevel" = "$primary_path" ]; then
  echo "livespec: refusing commit/push at primary checkout ($toplevel); use a worktree" >&2
  exit 1
fi

# Delegate to lefthook at worktrees so the repo's existing gates fire.
hook_name="$(basename "$0")"
exec mise exec -- lefthook run "$hook_name" "$@"

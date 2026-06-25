# dev-tooling/ — repo-tracked hook scripts and bootstrap fixtures

This directory is reserved for repo-tracked shell scripts and bootstrap
fixtures that are deployed into `.git/hooks/` or otherwise read by the
`just bootstrap` recipe. They are NOT Python modules; the
enforcement-suite (`livespec_dev_tooling/` package) does not import them.

## Authority

The canonical commit-refuse hook body is NO LONGER a script in this
directory. It is the `CANONICAL_HOOK_BODY` string constant in the
installer module
`livespec_dev_tooling/install_commit_refuse_hooks.py`, which is the
SINGLE source of truth — `just install-commit-refuse-hooks` (invoked by
`just bootstrap`) and CI both install it by running that installer, so
there is no second on-disk copy to drift. The body is wheel-carried as a
Python string because only the `livespec_dev_tooling/` package is
packaged (no `data/` resource dir).

Per `livespec/SPECIFICATION/non-functional-requirements.md`
§"Primary-checkout commit-refuse hook" and §"Commit-refuse hook
bootstrap procedure", every livespec-governed repository MUST host a
canonical commit-refuse hook at `.git/hooks/pre-commit`,
`.git/hooks/pre-push`, and `.git/hooks/commit-msg`. The structural body
refuses to run at the primary checkout (where `git rev-parse --git-dir`
equals `git rev-parse --git-common-dir`) UNLESS `git config
livespec.sandboxExempt` is `true`, and is a silent no-op at secondary
worktrees (whose git-dir differs). It is armed on install — no
`livespec.primaryPath` arming step, so no fail-open window. After the
refuse check passes, the body delegates to `lefthook run <hook-name>` so
the existing pre-commit / pre-push / commit-msg gates continue to fire.

The verifier
`livespec_dev_tooling/checks/primary_checkout_commit_refuse_hook_installed.py`
still ACCEPTS the retired legacy body (`git rev-parse --show-toplevel`
/ `livespec.primaryPath`) alongside the structural one, so a repo that
has not re-bootstrapped onto the structural installer stays green during
the fleet migration.

## Constraints

- Scripts in `dev-tooling/` MUST be portable POSIX shell (no bashisms).
- A new repo-tracked hook script added here that `just bootstrap`
  deploys requires updating the corresponding `bootstrap:` step in the
  `justfile` and (where applicable) the verifier that confirms it landed
  at the right path. The commit-refuse hook is now installed via the
  package installer module rather than a script here.

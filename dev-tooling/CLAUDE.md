# dev-tooling/ — repo-tracked hook scripts and bootstrap fixtures

Files in this directory are deployed into `.git/hooks/` or otherwise read
by the `just bootstrap` recipe. They are NOT Python modules; the
enforcement-suite (`livespec_dev_tooling/` package) does not import them.

## Authority

The canonical commit-refuse hook body at
`dev-tooling/livespec-commit-refuse-hook.sh` is the source of truth for
the canonical hook body referenced by:

- `livespec_dev_tooling/checks/primary_checkout_commit_refuse_hook_installed.py`
  (the doctor invariant verifying the hook is installed at the primary).
- `justfile` `bootstrap:` recipe (the installer that copies the script
  into `.git/hooks/pre-commit` and `.git/hooks/pre-push`).

Per `livespec/SPECIFICATION/non-functional-requirements.md`
§"Primary-checkout commit-refuse hook" and §"Commit-refuse hook
bootstrap procedure", every livespec-governed repository MUST host a
canonical commit-refuse hook at both `.git/hooks/pre-commit` and
`.git/hooks/pre-push`. The hook refuses to run at the primary checkout
(comparing `git rev-parse --show-toplevel` to the
`livespec.primaryPath` git-config entry) and is a silent no-op at
secondary worktrees. After the refuse-at-primary check passes, the
canonical hook delegates to `lefthook run <hook-name>` so the existing
pre-commit / pre-push gates continue to fire.

## Constraints

- Scripts in `dev-tooling/` MUST be portable POSIX shell (no bashisms).
- The canonical hook body MUST carry the marker comment
  `# livespec commit-refuse hook` plus the `git rev-parse --show-toplevel`
  invocation plus an `exit 1` branch — the doctor invariant matches
  these substrings as the canonical fingerprint.
- Adding a new script here requires updating the corresponding installer
  step in `justfile` `bootstrap:` and (where applicable) the doctor
  invariant that verifies it landed at the right path.

# fleet_git_credential_helper — the fleet clones' git credential helper shim

On the dev host, each fleet clone's `.git/config` sets

```ini
[credential "https://github.com"]
    helper = !/home/ubuntu/.local/bin/livespec-agent-github-credential-helper
```

That shim mints a GitHub App installation token for git through
livespec-runtime's `livespec-github-credential-helper`. It was installed by
hand on 2026-07-02 (livespec-orslcm Pillar 3). This role is now its committed
owner.

The role writes the shim and nothing else. It never edits a clone's
`.git/config` and never authenticates to GitHub.

## Why it has two routes

The hand-installed shim had one line:

```sh
exec /usr/local/bin/with-livespec-env.sh -- /data/projects/livespec-runtime/.venv/bin/livespec-github-credential-helper "$@"
```

That line ignores the clone's committed `credential_wrapper`. After the
livespec-ai organization transfer, the bare family wrapper projects the
personal App (3668528), and livespec-ai repositories refuse it. One agent push
was refused with `Permission to livespec-ai/livespec-dev-tooling.git denied to
thewoolleyman-factory-bot[bot]` (push gate 20261115T161424Z-520508).

The shim now picks a route per clone:

| The clone | The shim runs |
|---|---|
| its committed `.livespec.jsonc` names `GITHUB_APP_ID_ORG` (route C), and the tenant wrapper is installed | `TW_REPO=<clone> <tenant wrapper> -- <helper> <git's args>` |
| anything else | `<family wrapper> -- <helper> <git's args>`, the original path |

The tenant wrapper resolves the clone's committed `credential_wrapper`. For
route C, that maps the org App pair onto `GITHUB_APP_ID` and
`GITHUB_PRIVATE_KEY`. Clones that do not remap, such as homelab and
hetzner-xubuntu-info, keep the original path.

The tenant wrapper is installed by role `reconcile_runs` once
livespec-dev-tooling#4796 lands. The shim tests for it at run time, so until
then every clone keeps the original path. After it is installed, the
`GITHUB_APP_ID_ORG` grep can be dropped so that every clone goes through the
tenant wrapper. The wrapper falls back to the family wrapper by itself when a
clone commits no `credential_wrapper`.

## Variables

```yaml
fleet_git_credential_helper_dest: /home/ubuntu/.local/bin/livespec-agent-github-credential-helper
fleet_git_credential_helper_owner: ubuntu
fleet_git_credential_helper_group: ubuntu
fleet_git_credential_helper_mode: "0775"
fleet_git_credential_helper_runtime_helper: /data/projects/livespec-runtime/.venv/bin/livespec-github-credential-helper
fleet_git_credential_helper_family_wrapper: /usr/local/bin/with-livespec-env.sh
fleet_git_credential_helper_tenant_wrap: /usr/local/libexec/livespec-tenant-wrap.sh
```

`fleet_git_credential_helper_dest` is the path every clone's config already
names. Moving it orphans that config.

## Preconditions (asserted before any change)

The runtime helper and the family wrapper must be executable files. Without
them, every git operation that asks for a credential would fail. The tenant
wrapper is optional.

## Which hosts carry it

Measured 2026-11-15:

- vps (vmi3006760) carries the shim.
- hetzner-xubuntu does not. Its clones use the global `!gh auth git-credential`,
  the maintainer's OAuth login.
- Other hosts are not yet measured.

The play applies this role to `dev_hosts`, which is vps alone. A host found to
carry the shim later gets the same tag.

## Read-back (an operator runs it; the role does not)

From a livespec-dev-tooling worktree on the host:

```bash
GIT_TERMINAL_PROMPT=0 git push --dry-run origin HEAD:refs/heads/readback-nonexistent-branch
```

A dry-run push authenticates `git-receive-pack` and writes nothing. Success
means the shim minted a token the livespec-ai organization accepts, which is
the org App. A `403 ... denied to thewoolleyman-factory-bot[bot]` means the
clone took the original path.

Converge with:

```bash
/usr/local/bin/with-livespec-env.sh -- just ansible-drift ansible/dev-host.yml --tags fleet_git_credential_helper
/usr/local/bin/with-livespec-env.sh -- just ansible-apply ansible/dev-host.yml --tags fleet_git_credential_helper
```

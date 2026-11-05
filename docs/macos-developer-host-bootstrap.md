# macOS developer-host first touch

`just bootstrap` provisions repository-local obligations. Prepare the host first
under its machine-info repository's package policy; the governing requirements
are in [Developer host platforms](../SPECIFICATION/non-functional-requirements.md#developer-host-platforms).
A reconciled checkout alone does not prove ledger authentication, delegated gates,
or native container builds.

## Resolve tools in the shells that run hooks

Measure both a noninteractive login shell and a new interactive login shell.
Bare `python3` must resolve to the uv-installed default satisfying the repository's
`.python-version` and `requires-python`; Bash must be at least 4; Node comes from
mise. Existing mise Python or beads shims can shadow the intended host tools.
Keep `/usr/local/bin/bd` ahead of those shims and keep uv's `~/.local/bin/python3`
ahead of the system interpreter. Check the resolved executable and actual version,
then exercise a harmless command. Preserve other managed installations rather
than removing unrelated consumers.

On Homebrew hosts, declare prerequisites in the canonical host Brewfile before
running Bundle with `--no-upgrade`. Use the maintained versioned beads formula
matching the VPS's current `bd-real`, behind the Darwin-capable guard; scope tap
trust to the required formulae. Obtain the kubectl pin from the current
`ansible/roles/gates_kubeconfig/defaults/main.yml`, not the newest unversioned
formula. Report an unrelated Bundle install failure separately from a later
successful dependency-presence check.

## Separate ledger transport, pointers and authentication

Use the approved per-user SSH LaunchAgent forwarding `127.0.0.1:3307` to the VPS's
loopback. Test port reachability and reconnection by terminating only that
service's SSH child. Login-time automatic startup is a separate check. Reuse the
server-stable `.beads/metadata.json` pointer with owner-only permissions; never
run `bd init` or create a substitute store.

The canonical credential-wrapper factory uses the login Keychain on Darwin.
A locked Keychain can return `User interaction is not allowed` even for
`security show-keychain-info`. Local login/unlock through macOS is then required;
never guess a password or weaken Keychain policy. Keep credentials out of logs,
files and process arguments. `security add-generic-password` documents placing
`-w` last to prompt; a host-side adapter can feed that prompt through a private
PTY instead of forwarding a token as a child-process argument. Keep the factory
and generated wrapper bytes unchanged. Verify the installed wrapper through
presence-only probes and an actual tenant read after unlocking.

## Reconcile plugins and prove the delegated route

Inspect Codex marketplace sources before registering them. An existing unpinned
Git source can conflict with the same repository requested at `--ref release`.
Back up host config and reconcile only the affected registrations to the current
released-source contract; preserve unrelated marketplaces and authentication.
Use the CLI's plugin list to read back versions after bootstrap.

Reproduce the gate role's scoped client end state on Darwin: a dedicated local
group, the role's refresh/wrapper scripts, non-secret refresh configuration,
and a group-readable kubeconfig. Select a free local GID. Verify create-Job
permission and denied delete-Job/Secret reads. No namespace or cluster-policy
change is needed. A real authorized worktree change must receive its actual
terminal delegated-gate verdict before the push is counted as proof.

For native container builds, preserve the default Docker context and use an
explicit separate Lima builder context. Verify Linux arm64 execution, a local
build and the resulting image's behavior. Keep the Lima update pin coordinated
and preserve VM disks on rollback. None of these developer-host steps enrolls
a worker or establishes CI/factory readiness.

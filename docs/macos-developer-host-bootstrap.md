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
Verify access in the actual terminal audit/security session that will run the
factory and wrappers: an unlocked desktop session does not establish terminal
access. If needed, the maintainer can enter the login password at the native
hidden `security unlock-keychain` prompt in that same terminal. Never collect
that password in chat, argv or files, guess it, or weaken Keychain policy.

Keep the factory source and generated wrapper bytes unchanged. Adapt only host
storage, keeping service-account tokens out of child argv, files, history and
logs. Native `security add-generic-password -w` password entry, including a
private PTY, is unsuitable for service-account tokens: on a measured host it
silently stored only 128 bytes of an 852-byte token. Use bounded `security -i`
stdin commands held in memory, or a suitable native API with equivalent access
controls. For stdin commands, validate the token alphabet and identifier syntax,
exclude command-parser quotes/escapes/control characters, and enforce the native
4096-byte command-line bound including delimiters. Do not feed a token into an
unlock or authorization prompt.

Creation must grant the generated wrapper's reader alone with
`-T /usr/bin/security`, never `-A`. Reuse a readable byte-identical existing
value without writing. Refuse other mismatches unless an explicitly authorized,
verified repair applies; for example, an existing exactly-128-byte strict prefix
of the approved full source after confirmed truncation. On such an update use
`-U` without `-T` to preserve the existing ACL rather than reauthorizing it.
A nonzero native update may already have changed data: stop and inspect filtered
readback evidence instead of blindly retrying.

Before production storage, prove the actual writer/reader path with unique
nonsecret fixtures longer than 128 and 1024 bytes and clean up only those owned
items. Require full byte-identical readback of every successful stored token;
a successful write exit alone is insufficient. Then verify the exact provider
environment operation, unchanged generated-wrapper bytes, presence-only wrapper
probes and an authenticated tenant read. Publish canonical entry points only
after the complete validations pass.

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

# livespec_dev_tooling/worktree_pack/

Package-data holding the canonical worktree-discipline pack — the two
scripts `worktree-lib.sh` (portable worktree-lifecycle core) and
`branch-protection.sh` (server-side branch-protection mirror), plus the two
justfile fragments `worktree.just` (the four `just worktree-*` lifecycle
recipe stanzas) and `branch-protection.just` (the `protect-default-branch` /
`check-branch-protection` recipe stanzas), each `import`ed by the consumer
root justfile. These files are the SINGLE canonical source:
`install_worktree_pack` reads them (`__file__`-relatively) into the
`CANONICAL_*` constants it installs into a consumer's `dev-tooling/` (the
`.sh` scripts executable; the `.just` fragments non-executable, since they
are `import`ed, never run directly), and the
`primary_checkout_commit_refuse_hook_installed` verifier imports those same
constants to assert byte-identity against the installed copies.

They live here (as package-data, not as `.py` string constants) because the
shell carries lines longer than the 100-column lint limit; embedding them in
a module would force an `E501` per-file lint exemption. Do NOT edit these by
hand to fix a downstream drift — change the canonical source and re-run
`just install-worktree-pack`. ruff lints neither `.sh` nor `.just`, so these
files are exempt from the Python style gates by file type, not by carve-out.

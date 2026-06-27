# livespec_dev_tooling/worktree_pack/

Package-data holding the canonical worktree-discipline pack scripts —
`worktree-lib.sh` (portable worktree-lifecycle core) and
`branch-protection.sh` (server-side branch-protection mirror). These `.sh`
files are the SINGLE canonical source: `install_worktree_pack` reads them
(`__file__`-relatively) into the `CANONICAL_*` constants it installs into a
consumer's `dev-tooling/`, and the
`primary_checkout_commit_refuse_hook_installed` verifier imports those same
constants to assert byte-identity against the installed copies.

They live here (as package-data, not as a `.py` string constant) because
the shell carries lines longer than the 100-column lint limit; embedding
them in a module would force an `E501` per-file lint exemption. Do NOT edit
these by hand to fix a downstream drift — change the canonical source and
re-run `just install-worktree-pack`. ruff does not lint `.sh`, so these
files are exempt from the Python style gates by file type, not by carve-out.

# livespec_dev_tooling/worktree_pack/

Package-data holding the canonical worktree-discipline pack — seven
installed files from the six sources here: the four scripts
`worktree-lib.sh` (portable worktree-lifecycle core),
`branch-protection.sh` (server-side branch-protection mirror), `gate-run.sh`
(the detached gate runner), and `check-no-workflow-edits.sh` (the fleet's
ONE workflow-edit guard: an authorship control at the agent boundary whose
only override is a tracked per-change declaration verified against a
human-set `approval:workflow-edit` ledger label — no environment escape of
any kind; livespec-dev-tooling-fy02), plus the two justfile fragments
`worktree.just` (the four `just worktree-*` lifecycle recipe stanzas) and
`branch-protection.just` (the `protect-default-branch` /
`check-branch-protection` recipe stanzas), each `import`ed by the consumer
root justfile; the seventh installed file is the generated `.gitignore`.
These files are the SINGLE canonical source:
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

# Per-repository incident CI inventories

One released inventory per adopting repository, at `<owner>/<repo>.json`. The
released incident CI entrance looks an inventory up by the repository its
authenticated pull-request read names, and refuses a repository with no file
here as `incident-inventory-undeclared`. livespec-dev-tooling's own inventory
is not in this directory: it stays at `../incident-ci-inventory.json` and is
rendered from this tree.

Never edit an entry by hand. Render it with
`just render-incident-ci-inventory <owner/repo> <clone> <commit>` from the
adopter's own `.github/workflows/ci.yml` and `check-targets.txt` at a commit of
its default branch. The script records that commit as the entry's `source` and
writes the exact source bytes, with their git blob ids, under
`tests/fixtures/incident_ci_inventory_sources/<owner>/<repo>/`.
`tests/livespec_dev_tooling/test_incident_ci_inventory_sources.py` proves each
entry equals a fresh render of those bytes. Re-render on a newer default-branch
commit whenever the adopter adds, removes or renames a CI target or changes an
`# incident-timing:` annotation; the change reaches CI with the next release.
See `docs/incident-ci-entry.md` in livespec-dev-tooling.

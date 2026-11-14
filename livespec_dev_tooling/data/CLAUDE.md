# Packaged incident data

The incident CI inventories ship with approved controller code, one per adopting repository under `incident-ci-inventory/<owner>/<repo>.json` (this repository's own stays at `incident-ci-inventory.json`). Each derives only from that repository's normal workflow's contributed check-target set and from each member's `# incident-timing:` annotation in its `check-targets.txt`. Regenerate this repository's own entry through `incident_ci_inventory.render_inventory(workflow=..., inventory=...)`, and an adopter's through `just render-incident-ci-inventory <owner/repo> <clone> <commit>` (which records the adopter's default-branch commit as the file's `source`), when a target is added, removed or renamed, or when a timing annotation changes; no digest of the workflow or of the inventory is pinned anywhere. The entrance refuses a repository with no file as `incident-inventory-undeclared`. Each normal workflow remains the source of its complete member graph.

## Packaged runtime assets

This directory carries installable runtime assets shipped with the Python wheel.
The incident observer unit is a provisioning template. Editing or packaging it
does not install a service, provision credentials, grant a recovery principal or
activate incident mode. Its release and protected host installation requirements
are documented in `docs/incident-observer-service.md`.

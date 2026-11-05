# Packaged incident data

The incident CI inventory ships with approved controller code. It derives only from the normal workflow's contributed check-target set, so regenerate it through `incident_ci_inventory.render_inventory` only when a target is added, removed or renamed; no digest of the workflow or of the inventory is pinned anywhere. The normal workflow remains the source of its complete member graph.

## Packaged runtime assets

This directory carries installable runtime assets shipped with the Python wheel.
The incident observer unit is a provisioning template. Editing or packaging it
does not install a service, provision credentials, grant a recovery principal or
activate incident mode. Its release and protected host installation requirements
are documented in `docs/incident-observer-service.md`.

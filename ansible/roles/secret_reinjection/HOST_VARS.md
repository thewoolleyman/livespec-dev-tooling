# secret_reinjection -- per-host values for the inventory

None. The role is server-only: `ci-pool.yml` gates it on `cluster_role ==
'server'`, and every value it reads is a role default.

## Out-of-band, not provisioned here

The role installs each injector and its oneshot unit and ENABLES the unit for
the next boot; it never starts one, because running a unit applies its Secret
live to the cluster. The credentials the units decrypt live in
`/etc/credstore.encrypted` and are put there by a human, not by the role.

### Post-apply steps an operator still performs

1. **Seed the GitHub App credstore, once per rebuilt server, attended.** As a
   member of the `github-ci-runners` group, run
   `with-github-ci-runners-env.sh -- seed-github-app-creds.sh`. It writes
   `arc-github-app-id`, `arc-github-app-installation-id` and
   `arc-github-app-private-key`. Until it has run, the boot unit
   `inject-github-app-secret.service` fails at every boot and the ARC runners
   have no credential. The role cannot assert it: it must stay possible to arm
   the units in either order, so it prints a warning for each credential that is
   missing and the converge continues. Treat that warning as this step still
   owed.
2. **Seed the gate forge token the same way.** Run `seed-gate-forge-cred.sh`
   under the same wrapper to write `gate-forge-token`, which
   `inject-gate-forge-secret.service` decrypts.

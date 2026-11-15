# secret_reinjection -- per-host values for the inventory

None. The role is server-only: `ci-pool.yml` gates it on `cluster_role ==
'server'`, and every value it reads is a role default.

## The organization projection (livespec-dev-tooling-h5r75q)

Beside the two credstore-backed units, the role installs
`inject-github-app-secret-livespec-ai.service`, which writes the
`livespec-ai-arc` GitHub App credential (App 5765497, installation 182096616)
into the Secret `arc-github-app-installation-livespec-ai` in `arc-runners`,
the Secret the scale sets registered at the `livespec-ai` organization use.
The personal-account Secret `arc-github-app-installation` stays the sibling
unit's and is never named by this one.

- **Source.** Only the environment that homelab's shared-credentials launcher
  (installed by the `shared_credentials_host` role) builds for consumer
  `livespec-ai-arc`: `LIVESPEC_AI_ARC_APP_ID`,
  `LIVESPEC_AI_ARC_INSTALLATION_ID`, `LIVESPEC_AI_ARC_PRIVATE_KEY`, read at
  launch from the SSM parameters under
  `/gitops/v1/shared/providers/github/livespec-ai-arc/`. No credstore entry,
  no `$CREDENTIALS_DIRECTORY`, nothing sealed for it on the host.
- **Who runs it.** The dedicated system user `arc-org-projector` (no login
  shell). `/etc/sudoers.d/arc-org-projector` lets it run exactly one
  fully-argumented command as root, the launcher's `launch --manifest
  /etc/livespec-ci-credentials/<host>.json --consumer livespec-ai-arc --
  /usr/local/lib/ci-runner-k3s/inject-github-app-secret-livespec-ai.sh`; the
  launcher drops back to that user for the injector.
- **Its Kubernetes identity survives the tmpfs datastore.** It is a client
  certificate (CN `arc-org-projector`, no group) signed by the k3s client CA,
  which lives on disk, in `/etc/arc-org-projector/kubeconfig`
  (`root:arc-org-projector 0640`). A ServiceAccount token would die with the
  datastore at every reboot. The unit's root `ExecStartPre=+`,
  `ensure-arc-org-projector-access.sh`, re-applies the Role and RoleBinding
  (`arc-org-projector-rbac.yaml`: `get`, `update`, `patch` on that ONE Secret
  by `resourceNames`), creates the Secret EMPTY when it is absent (RBAC cannot
  name-scope `create`), re-mints the certificate when it is missing, no longer
  verifies against the client CA or is within 30 days of expiry, and reads the
  grant back by impersonation, failing if the user can read the personal
  Secret, list Secrets or create one.
- **Failure.** A missing or empty value makes the injector exit 1, naming each
  missing variable, before any cluster call; the Secret keeps its last value.

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
3. **Nothing to seed for the organization projection.** Its three values come
   from AWS SSM through the launcher, so it needs only the `shared_credentials_host`
   role's converge and its one-time bootstrap-key delivery. Until that key is
   sealed, `inject-github-app-secret-livespec-ai.service` fails at boot (the
   launcher cannot read the parameters) and leaves the organization Secret as
   the empty placeholder.

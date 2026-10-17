# `sandbox_driver_kubernetes` — the Kubernetes sandbox-driver plugin on a Fabro-server host

**What it is for.** Plan `kubernetes-sandbox-backend` (livespec-orchestrator-beads-fabro
epic `bd-ib-nmuyjc`) moves the factory's sandboxes onto the maintainer-owned
cluster. The plugin, [`sandbox-driver-kubernetes`](https://github.com/thewoolleyman/sandbox-driver-kubernetes),
runs beside the Fabro worker on this host and creates each sandbox as a pod in
the `factory` namespace. This role installs it and the upstream `lithos-sandbox`
CLI that drives it, both pinned by a committed digest, and renders their
configuration. Work-item `bd-ib-nmuyjc.3`.

**No per-host values.** The account and home come from `fabro_server`'s own
host_vars (`fabro_server_host_user`, `fabro_server_host_group`,
`fabro_server_host_home`), the credential path from `factory_kubeconfig`'s
defaults, and every cluster fact from the factory delivery, which is the same on
every sandbox host. A host whose Fabro instance runs the plugin under a
different HOME sets `sandbox_driver_kubernetes_config_homes`.

## Variables

| variable | default | meaning |
| --- | --- | --- |
| `sandbox_driver_kubernetes_version` | the pinned release tag | plugin release to install |
| `sandbox_driver_kubernetes_sha256` | the release asset's digest | the plugin's committed digest, also written into the CLI profile |
| `sandbox_driver_kubernetes_cli_rev` | the sandbox-driver revision the plugin pins | the CLI's source revision |
| `sandbox_driver_kubernetes_cli_sha256` | the release asset's digest | the CLI's committed digest |
| `sandbox_driver_kubernetes_config_homes` | `[fabro_server_host_home]` | every HOME the plugin is launched under |
| `sandbox_driver_kubernetes_workspace_root` | `/srv/factory-workspaces` | the persistent per-node workspace root (livespec-dev-tooling-due2h6) |
| `sandbox_driver_kubernetes_tolerations` | the factory taint, plus indefinite `not-ready` and `unreachable` NoExecute tolerations | taints sandbox pods tolerate; overriding the list drops the node-outage pair unless it is restated |

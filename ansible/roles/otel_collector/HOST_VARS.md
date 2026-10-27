# `otel_collector` — per-host values for the inventory's `host_vars`

One role, four host postures. `thewoolleyman/otel-collector` carries one
collector configuration per posture, and each host names its own; every default
in `defaults/main.yml` is the DEV HOST's, so a host that declares nothing
resolves to that host's shape rather than to an error.

**Why the pool nodes are here at all.** Their collectors were installed by
`scripts/install-ci-runner-host.sh` and `scripts/install-hp-factory-host.sh` in
the collector repository, and the fleet host guard refuses any by-hand host
change — so those installers can no longer be run and a node rebuilt from empty
storage had no path to a collector. `ansible/ci-pool.yml` applies this role
UNGATED to every pool node, because
`SPECIFICATION/non-functional-requirements.md` §"Runner-pool node telemetry"
governs every node "whatever its `cluster_role` or factory posture" and a gated
role would leave the node it excluded indistinguishable from one that had gone
silent.

**What the role owns, and what stays a precondition.** On a pool node it owns
the `otel-collector` system account, the pinned `otelcol-contrib` binary, the
merged configuration at `/etc/otel-collector/config.yaml`, the unit, and the
ingest-key line it appends to `/etc/otel-collector/.env`. A host declaring
`otel_collector_cluster_identity: true` also gets the merged RBAC manifest,
identity render script, and enabled identity unit from the configured collector
ref; a changed one runs the identity unit before restarting the collector. The
CI-runner host's `host.env` remains a node fact and precondition. The kubeconfig
is a post-check because the role's identity unit renders it after every change.

**The environment file.** The role APPENDS each key named in
`otel_collector_env_from_controller` that the file does not already set, under
`no_log`, with the value read from the control node's environment — so the apply
must run under the credential wrapper. It never rewrites a key the file already
sets, which is what keeps the factory host's hand-placed agent-activity key
exactly as placed, and it creates the file 0600 `root:root` on a host that has
none.

| variable | default | meaning |
| --- | --- | --- |
| `otel_collector_config_file` | `config.yaml` | which configuration this host runs out of the collector repository |
| `otel_collector_config_ref` | `main` | the ref it is read at; a sha holds or rolls back a host |
| `otel_collector_user` / `_group` | `ubuntu` | the account the collector runs as |
| `otel_collector_user_groups` | `[]` | further groups that account is appended to (`docker` where the configuration reads the engine socket) |
| `otel_collector_manage_install` | `false` | create the system account and install the pinned binary, instead of asserting the binary |
| `otel_collector_binary_version` | `0.147.0` | the pinned release |
| `otel_collector_binary_arch` / `_host_architecture` / `_sha256` | `amd64` / `x86_64` / (the amd64 tarball's) | the release asset, the machine it is for, and its checksum — overridden together or not at all |
| `otel_collector_extra_environment_files` | `[]` | further `EnvironmentFile=` entries, listed BEFORE the ingest-key one so a value there wins |
| `otel_collector_cluster_identity` | `false` | install and run the CI-runner host's RBAC, identity renderer and identity unit from the configured collector ref |
| `otel_collector_kubeconfig_path` | `""` | the scoped read-only cluster identity; empty means this host reads no kubelet |
| `otel_collector_unit_description` | the dev host's | the unit's `Description=` |
| `otel_collector_unit_after` / `_wants` | `network-online.target docker.service` | the unit's start order |
| `otel_collector_hardened` | `false` | add `ProtectSystem=strict`, `ProtectHome`, `PrivateTmp` and a read-only `/etc/otel-collector` |
| `otel_collector_env_from_controller` | `[]` | control-node variables to append to the environment file when it lacks them |

```yaml
# poweredge-xubuntu — the CLUSTER-READING collector, the one node whose
# configuration discovers every kubelet from the API server and scrapes it.
otel_collector_config_file: config.ci-runner-host.yaml
otel_collector_user: otel-collector
otel_collector_group: otel-collector
otel_collector_manage_install: true
otel_collector_hardened: true
otel_collector_cluster_identity: true
otel_collector_extra_environment_files:
  - /etc/otel-collector/host.env
otel_collector_kubeconfig_path: /etc/otel-collector/kubeconfig
otel_collector_unit_after: network-online.target k3s.service otel-collector-identity.service
otel_collector_unit_wants: network-online.target otel-collector-identity.service
otel_collector_env_from_controller:
  - HONEYCOMB_INGEST_KEY_LIVESPEC
```

```yaml
# gmktec-xubuntu — a plain k3s agent: host metrics only, no cluster identity,
# no Docker socket, so its unit follows neither k3s nor docker.
otel_collector_config_file: config.k3s-agent-host.yaml
otel_collector_user: otel-collector
otel_collector_group: otel-collector
otel_collector_manage_install: true
otel_collector_hardened: true
otel_collector_unit_after: network-online.target
otel_collector_unit_wants: network-online.target
otel_collector_env_from_controller:
  - HONEYCOMB_INGEST_KEY_LIVESPEC
```

```yaml
# hp-xubuntu — the factory host: host metrics plus the engine's container stats,
# which is what the account's `docker` membership is for. Its start order is the
# role's default already.
otel_collector_config_file: config.hp-factory.yaml
otel_collector_user: otel-collector
otel_collector_group: otel-collector
otel_collector_manage_install: true
otel_collector_hardened: true
otel_collector_user_groups:
  - docker
otel_collector_env_from_controller:
  - HONEYCOMB_INGEST_KEY_LIVESPEC
```

## Operator procedure

A converge that changes nothing notifies nothing, so the collector is left
exactly as it was found — which is what makes an apply safe to run as often as a
drift report. A changed configuration or unit is put into the running process by
the role's handler, and the service is otherwise only ever brought up, never
cycled.

1. `/usr/local/bin/with-livespec-env.sh -- just ansible-drift ansible/ci-pool.yml --tags otel_collector`
   and read it. The wrapper is what projects the ingest key the preflight reads;
   without it the run refuses, naming the variable.
2. `/usr/local/bin/with-livespec-env.sh -- just ansible-apply ansible/ci-pool.yml --tags otel_collector`.
3. Positive control: each node's host metrics reach the fleet observability
   surface stamped with `host.name` equal to that node's name, and the
   CI-runner host's kubelet rows arrive attributed by `k8s.node.name`.

**Rollback.** Set `otel_collector_config_ref` to the previous sha and re-run
step 2. The pinned binary is rolled back by moving
`otel_collector_binary_version`, `_arch`, `_host_architecture` and `_sha256`
together to the previous release's own values.

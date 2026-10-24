# `otel_collector` — per-host values for the inventory's `host_vars`

The host's own OpenTelemetry Collector, `otel-collector.service`. One role
serves two plays and four hosts: `ansible/dev-host.yml` converges the
maintainer's dev host (`vps`, livespec-dev-tooling-x36is7) and
`ansible/ci-pool.yml` converges every `ci_pool` node — the server, the CI agent
and the factory-only agent (livespec-dev-tooling-ool6ws).

**Why the pool nodes are here.** Their collectors were installed by HAND-RUN
scripts in `thewoolleyman/otel-collector` (`scripts/install-ci-runner-host.sh`
on poweredge, `scripts/install-hp-factory-host.sh` on hp) and nothing in
`ansible/ci-pool.yml` named a collector; gmktec had no installer at all. The
fleet host guard refuses a by-hand host change, so those installers can no
longer be run: this role is the only path by which a merged configuration
reaches a node. `SPECIFICATION/non-functional-requirements.md` §"Runner-pool
node telemetry" says it outright — every pool node's collector, its
configuration, its unit, its pinned binary and its ingest-key environment entry
MUST be converged by `ansible/ci-pool.yml`, and a hand-run installer MUST NOT be
the deployment path.

**The role entry is UNGATED.** It is gated on none of `ci-pool.yml`'s four
posture axes (`cluster_role`, `CI_NODE_FACILITIES`, `FACTORY_NODE`, or any
other): the section governs every node "whatever its `cluster_role` or factory
posture", and a collector running on a subset leaves the rest of the pool's load
invisible and their dead-man triggers unfireable. Everything that genuinely
varies per node is a variable below.

**What the role owns, and what it only asserts.** It owns the merged
configuration at `/etc/otel-collector/config.yaml`, the unit, and — where
`otel_collector_manage_install` is set — the dedicated `otel-collector` system
user and the pinned `otelcol-contrib` binary. It ASSERTS, and never writes,
`otel_collector_kubeconfig_path` and every file in
`otel_collector_extra_environment_files`: those belong to the collector
repository's installer and to `otel-collector-identity.service`, and a converge
that invented them would be converging a credential it must not hold.

**The environment file.** `otel_collector_environment_path` carries the
Honeycomb ingest keys the merged configuration reads as `${env:...}`, and the
unit names it in `EnvironmentFile=`. The converge derives the required keys FROM
the merged configuration — so the preflight cannot go stale when the collector
repository adds or drops one — and looks for each across every file the unit
names, because poweredge's `HONEYCOMB_API_ENDPOINT` lives in its non-secret
`host.env` rather than in the secret file. A host that names keys in
`otel_collector_env_from_controller` has each MISSING one APPENDED from the
control node's own environment (the credential wrapper projects the value),
under `no_log`, and a key the file already sets is never rewritten: hp's file
already carries the agent-activity keys. A key the control node does not set is
refused BY NAME before anything is written.

| variable | default | meaning |
| --- | --- | --- |
| `otel_collector_config_file` | `config.yaml` | which merged configuration file in `thewoolleyman/otel-collector` this host runs |
| `otel_collector_config_ref` | `main` | the ref that file is read at; a sha holds or rolls back a host |
| `otel_collector_user` / `otel_collector_group` | `ubuntu` | the account the collector runs as |
| `otel_collector_manage_install` | `false` | this converge owns the service account and the pinned binary, rather than only asserting the binary |
| `otel_collector_binary_version` | `0.147.0` | the pinned `otelcol-contrib` release |
| `otel_collector_binary_sha256` | (role default) | the digest upstream publishes for that release's amd64 tarball; bump both together |
| `otel_collector_extra_environment_files` | `[]` | further `EnvironmentFile=` entries, named BEFORE the secret file so its values win; asserted, never written |
| `otel_collector_kubeconfig_path` | `""` | the scoped read-only ServiceAccount kubeconfig, named as `Environment=KUBECONFIG=`; asserted, never written |
| `otel_collector_unit_after` | `network-online.target docker.service` | the unit's `After=` |
| `otel_collector_unit_wants` | `network-online.target docker.service` | the unit's `Wants=` |
| `otel_collector_hardened` | `false` | add `ProtectSystem=strict`, `ProtectHome`, `PrivateTmp` and `ReadOnlyPaths` to the unit |
| `otel_collector_env_from_controller` | `[]` | environment keys to APPEND from the control node's environment when the file lacks them |

```yaml
# vps (dev_hosts) — the default posture, stated by declaring nothing. Its
# collector predates this converge, runs as the login account, and scrapes the
# whole machine with hostmetrics, so hardening it is a behaviour change rather
# than a transcription and belongs to its own decision.
```

```yaml
# poweredge-xubuntu (ci_pool, k3s server) — the CI-runner-host shape
otel_collector_config_file: config.ci-runner-host.yaml
otel_collector_user: otel-collector
otel_collector_group: otel-collector
otel_collector_manage_install: true
otel_collector_hardened: true
otel_collector_extra_environment_files:
  - /etc/otel-collector/host.env
otel_collector_kubeconfig_path: /etc/otel-collector/kubeconfig
otel_collector_unit_after: network-online.target k3s.service otel-collector-identity.service
otel_collector_unit_wants: network-online.target otel-collector-identity.service
otel_collector_env_from_controller:
  - HONEYCOMB_INGEST_KEY_LIVESPEC
```

```yaml
# gmktec-xubuntu (ci_pool, k3s agent) — the k3s-agent shape, host metrics only
otel_collector_config_file: config.k3s-agent-host.yaml
otel_collector_user: otel-collector
otel_collector_group: otel-collector
otel_collector_manage_install: true
otel_collector_hardened: true
otel_collector_env_from_controller:
  - HONEYCOMB_INGEST_KEY_LIVESPEC
```

```yaml
# hp-xubuntu (ci_pool, factory-only agent) — the factory-host shape
otel_collector_config_file: config.hp-factory.yaml
otel_collector_user: otel-collector
otel_collector_group: otel-collector
otel_collector_manage_install: true
otel_collector_hardened: true
otel_collector_env_from_controller:
  - HONEYCOMB_INGEST_KEY_LIVESPEC
```

## Operator procedure

The ingest key the converge appends is projected into the control node's
environment by the credential wrapper, so BOTH commands run under it — the
drift report too, because its own preflight reads the same key and a dry run
without it refuses by name.

1. `/usr/local/bin/with-livespec-env.sh -- just ansible-drift ansible/ci-pool.yml --tags otel_collector`
   and read it.
2. `/usr/local/bin/with-livespec-env.sh -- just ansible-apply ansible/ci-pool.yml --tags otel_collector`.
3. Positive control: each node's kubelet and host-metric rows reach the fleet
   observability surface stamped with that node's `host.name`, and its dead-man
   trigger stays quiet.

A converge over a node whose managed files already match notifies nothing, so
the restart handler never runs and the collector is left exactly as it was
found — which is the property that makes an apply safe to run as often as a
drift report.

**Rollback.** Set `otel_collector_config_ref` to the previous sha of
`thewoolleyman/otel-collector` and re-run step 2; the configuration is the only
thing a ref change moves. A binary rollback is a change to
`otel_collector_binary_version` and `otel_collector_binary_sha256` together,
re-run the same way. Narrow either to one node with `-l <host>`.

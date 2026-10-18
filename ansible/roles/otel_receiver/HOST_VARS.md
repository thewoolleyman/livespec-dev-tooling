# `otel_receiver` — per-host values for the inventory's `host_vars`

The persistent OTel receiver a Fabro factory host's servers export their spans
to (livespec-dev-tooling-jvem). Each Fabro instance's `otel.conf` drop-in,
installed by `fabro_server`, points at `http://172.17.0.1:4318`; this role
installs the thing listening there. The listen address is the receiver's own
committed default (the Docker bridge gateway, port 4318); the unit sets no
override.

**Why it is a role.** Until 2026-10-17 hp's receiver was a hand-placed,
untracked `otel_receiver_daemon.py` running out of the factory's shared
orchestrator checkout, left at release 0.140.0. That build's attribute
allowlist predates the Petri-era `run_turn.command`, `run_turn.command.digest`,
`run_turn.env.keys` and `run_turn.status` names, so it stripped all four from
every hp-candidate span. Under `## Fabro factory host provisioning` a factory
service installed by hand is drift to express in the play, so it is expressed
here.

**What the role owns.** A clone of livespec-orchestrator-beads-fabro at
`otel_receiver_orchestrator_version` (a release tag, at or after
`v0.210.0`), under `~/.local/share/livespec-otel-receiver/`; the daemon entry
point in `files/`, installed beside it; the unit `otel-receiver.service`; and
the state directory `~/.local/state/livespec-otel-receiver/`. It never touches
`fabro_server_host_checkout`, which a live factory runs from. The old untracked
daemon file left in that checkout is no longer referenced by anything; it is
the checkout owner's to delete.

**The environment file.** `otel_receiver_env_file` carries
`HONEYCOMB_INGEST_KEY_LIVESPEC`, and the unit names it in `EnvironmentFile=`.
By default the role only checks that it exists. A host that sets
`otel_receiver_env_from_controller` has it RENDERED when it is absent, mode
0600, from that control-node variable (the credential wrapper supplies it); an
existing file is never overwritten and never read back.

| variable | default | meaning |
| --- | --- | --- |
| `otel_receiver_enabled` | `false` | install the receiver on this host |
| `otel_receiver_user` / `otel_receiver_group` | `ubuntu` | the account it runs as |
| `otel_receiver_home` | `/home/ubuntu` | that account's home |
| `otel_receiver_env_file` | (none; required) | the ingest-key environment file |
| `otel_receiver_env_from_controller` | `""` | control-node variable to render that file from when absent |
| `otel_receiver_orchestrator_version` | `v0.211.0` (role default) | the release the receiver runs |

```yaml
# hp-xubuntu (measured 2026-10-17 from the hand-installed unit)
otel_receiver_enabled: true
otel_receiver_user: cwoolley
otel_receiver_group: cwoolley
otel_receiver_home: /home/cwoolley
otel_receiver_env_file: /home/cwoolley/.fabro/storage/otel-receiver.env
```

```yaml
# gmktec-xubuntu (no file on the host; rendered from the credential wrapper)
otel_receiver_enabled: true
otel_receiver_user: cwoolley
otel_receiver_group: cwoolley
otel_receiver_home: /home/cwoolley
otel_receiver_env_file: /home/cwoolley/.fabro/storage/otel-receiver.env
otel_receiver_env_from_controller: HONEYCOMB_INGEST_KEY_LIVESPEC
```

## Operator procedure

A restart drops the spans every Fabro instance on the host exports while the
receiver is down, for about `RestartSec` (5 seconds) plus start-up. No run is
killed and none is held. So a converge that changes the receiver's source,
entry point or unit does NOT restart it unless the operator allows it; it
writes `restart-pending` in the state directory and reports the deferral, and
the next allowed run applies it.

1. Announce the window to whoever watches the host's telemetry.
2. `just ansible-drift ansible/fabro-hosts.yml --tags otel_receiver -l <host>`
   and read it.
3. `just ansible-apply ansible/fabro-hosts.yml --tags otel_receiver -l <host> -e otel_receiver_restart_allowed=true`.
4. Positive control: the next `run_turn` span from each Fabro instance on the
   host reaches Honeycomb with its `run_turn.command` attribute.

**Rollback.** Set `otel_receiver_orchestrator_version` back to the previous
tag and re-run step 3. The receiver keeps no state that a version change
invalidates.

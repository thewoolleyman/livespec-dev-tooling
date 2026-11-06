# incident_observer

Converges one fleet host to a running **independent released incident
observer** — the controller process `docs/incident-observer-service.md`
specifies, whose `/current` and `/admitted` answer the incident CI entrance's
read-only query (`docs/incident-ci-entry.md`). Work item
`livespec-dev-tooling-w7n3ad`, plan `expedited-incident-response-flag`.

```bash
/usr/local/bin/with-livespec-env.sh -- just ansible-drift ansible/dev-host.yml --tags incident_observer,tailscale_serve
/usr/local/bin/with-livespec-env.sh -- just ansible-apply ansible/dev-host.yml --tags incident_observer,tailscale_serve
```

Both run under the credential wrapper, because the role writes the three secret
files from the control node's projected environment (below). A bare run refuses
at its first task and names the variables; nothing is written.

## The host, and why

The role runs on the `dev_hosts` group, whose one member is **`vps`**. Of the
four inventory hosts it is the only one that already runs always-on fleet
control services behind a tailnet TLS front — `tailscale serve` publishes its
two Fabro servers and two further loopback services at `vps.perch-rudd.ts.net`
— and that is in neither `ci_pool` (the k3s CI nodes, whose runners are the
observer's callers) nor `sandbox_hosts` (the Fabro factory host `gmktec-xubuntu`,
which runs the petri server but executes candidate code in its sandboxes).
The controller's directory must live outside candidate checkouts, the tenant,
credential projection, factory and gates namespaces (`docs/incident-observer.md`),
which rules out every CI node and every sandbox host whatever their TLS posture.

## Which URL is tailnet-internal and which must be public

| Route | Caller | Reach |
| --- | --- | --- |
| `POST /current`, `POST /admitted` (query token) | the incident CI job on a self-hosted k3s runner | **tailnet-internal**: `https://vps.perch-rudd.ts.net:8765`, the `tailscale serve` mapping `vps` declares in `host_vars` (`:8765 -> http://127.0.0.1:8765`). The runners sit inside the tailnet, so nothing here needs a public address. |
| `POST /arm`, `/bind`, `/invalidate-ci` (control token) | the maintainer's independent host | tailnet-internal, the same mapping. |
| `POST /callback` (GitHub HMAC) | GitHub's `workflow_job` webhook delivery | **must be public**: `https://vps.perch-rudd.ts.net:10000/callback`, a path-scoped Tailscale Funnel the role publishes (`tailscale funnel --bg --https=10000 --set-path=/callback http://127.0.0.1:8765/callback`). Only that path is public; a request to any other path on port 10000 is not proxied, and the tailnet-only mapping above is untouched. Funnel admits ports 443, 8443 and 10000 only, and 8443 is already served here. |

## What the apply converges

- the system account `livespec-incident` (home `/var/lib/livespec-incident`,
  no login), distinct from the candidate account whose uid controller.json
  names (`incident_observer_candidate_user`, `ubuntu` on `vps`);
- `/opt/livespec-incident/venv` on the system interpreter, with the **released**
  `livespec-dev-tooling` tag installed from GitHub (`incident_observer_release`),
  never from a checkout on the host, re-installed only when the venv serves a
  different version;
- `/opt/livespec-incident/reader`: the orchestrator plugin at its released tag
  (`incident_observer_reader_release`), whose `incident_authority.py` is the
  canonical `read-current` reader the manifest names;
- `/var/lib/livespec-incident/reference`: the independent reference clone of the
  observed repository at the released tag, owned by the controller account, with
  a `livespec-incident-reference-fetch.timer` (every 5 min) keeping its objects
  current for the inverse;
- `/var/lib/livespec-incident/receipts` (mode 0700, outside the clone) with the
  recovery journal directories beneath it;
- the three secret files (`/etc/livespec-incident/{webhook,control,query}-secret`,
  mode 0600, owned by the controller account), written from the control node's
  environment under `no_log` — see the first maintainer step;
- `/etc/livespec-incident/reader.env` (mode 0600, owned by the controller
  account): `BEADS_DOLT_PASSWORD=…`, the canonical reader's tenant credential,
  written under `no_log` from the same wrapper-projected variable the control
  node already carries, and loaded by the unit's `EnvironmentFile=`. The reader
  subprocess inherits it, so it reads the tenant with credential projection
  inside the controller's own account — the shape the spec allows under
  `NoNewPrivileges`; the sudo wrapper is refused by the loader and the unit
  alike. The tenant's host and port (`127.0.0.1:3307`, the dolt-server on this
  host) come from the reference clone's committed `.beads/config.yaml`, not
  from this role;
- `/etc/livespec-incident/controller.json` with exactly the nine keys the loader
  demands, every value a host fact (paths from the role's layout, the candidate
  uid from `getent`, the repository and port from the role's defaults);
- `/etc/livespec-incident/released-installation.json`, rendered **on the host by
  the serving interpreter** with `files/render_released_installation.py`: the
  package digest over every installed `.py` in the loader's own order, the
  released tag and its commit (read from the reference clone), the reader and
  principal argv, the SHA256 of every executable they name plus the resolved
  interpreter, and the required master leaf jobs (`ci-green`, the only status
  check master's protection requires, measured 2026-11-05). The repository's
  `tests/livespec_dev_tooling/test_incident_observer_role.py` holds the renderer
  to the loader's algorithm;
- an isolated `ControllerInstallation.load` of the whole installation **as the
  controller account** before the unit is written, so a refusal names the apply
  rather than a unit exiting 2;
- `livespec-incident-observer.service`: the packaged provisioning template with
  `NoNewPrivileges=true`, `ProtectSystem=strict`, `ProtectHome=true`,
  `PrivateTmp=true`, `UMask=0077`, the cleared injection variables and a fixed
  `PATH`, executing
  `/opt/livespec-incident/venv/bin/python -I -m livespec_dev_tooling.incident_observer_service --config /etc/livespec-incident/controller.json`
  on loopback port 8765;
- a probe that `POST /current` without the query token is refused (403), which
  is also the proof the unit passed its installation check and bound its socket;
- the path-scoped Funnel for `/callback` (above), published only when the
  node's funnel status does not already carry it.

A second apply over a converged host reports no change: the install is gated on
the served version, both clones sit at tags, every file is compared by content,
the manifest is rendered to a register and installed only when its bytes differ,
and every restart lives in a handler. A `--check` on a host the role has never
reached writes nothing and says which steps an apply would perform.

The principal the manifest names is the packaged
`incident_recovery_journal_service.py`, the only schema-1 principal process this
release ships. It reserves and journals effects; it grants no forge capability.
A live recovery principal with branch-protection authority is a separate
provisioning the plan still owes, as `docs/incident-inverse.md` records.

## What a first apply does that later applies do not

A first apply creates the account, the venv and the release, and only then can
it render the manifest, load the installation and import the service module.
The role re-reads "is it installed" after it installs, so all three run on the
first apply and the unit starts verified; a dry run creates nothing and keeps
its pre-read answer. Beside the release the role installs `typing-extensions`
(`incident_observer_typing_extensions_requirement`): the released distribution
vendors its runtime and declares no dependency, but its vendored `returns`
imports that one module, and the release itself is installed with `--no-deps`.
The incident CI job installs it the same way.

## Maintainer-only steps

Each is outside what a committed, reversible change can do; the reason follows.
Steps 2 and 3 were performed by the maintainer on 2026-11-05 against exactly the
values this role renders; they are recorded here so the next host or rotation
knows what to redo.

1. **Create the three secrets in 1Password, environment
   `fufpvkvatwkmqjzvilvfnemsue` (the livespec environment the installed
   `/usr/local/bin/with-livespec-env.sh` projects), named
   `LIVESPEC_INCIDENT_WEBHOOK_SECRET`, `LIVESPEC_INCIDENT_CONTROL_SECRET` and
   `LIVESPEC_INCIDENT_QUERY_SECRET`, each at least 32 bytes and all three
   distinct, then run the apply through the wrapper** (the two commands at the
   top). Reason: the secrets must never exist in this repository, and only that
   environment is what the wrapper delivers to the control node, so that is the
   one place the apply can read them from. The reader's `BEADS_DOLT_PASSWORD`
   is already in that environment; nothing new is created for it.
2. **Done 2026-11-05 — the GitHub `workflow_job` webhook on
   `thewoolleyman/livespec-dev-tooling`**, delivering to
   `https://vps.perch-rudd.ts.net:10000/callback` with the webhook secret and
   JSON content type. Reason it is maintainer-held: a webhook subscription is a
   repository GitHub setting an agent never writes. The public ingress itself
   is the role's funnel task; if the tailnet policy does not grant this node
   the `funnel` attribute, that task fails naming the policy, and granting it
   is a tailnet-admin step.
3. **Done 2026-11-05 — the repository variable `LIVESPEC_INCIDENT_OBSERVER_URL`
   = `https://vps.perch-rudd.ts.net:8765` and the repository secret
   `LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN` = the query secret's exact bytes.**
   Reason: the trusted workflow supplies both to the incident CI job
   (`docs/incident-ci-entry.md`), and repository variables and secrets are
   maintainer-held GitHub settings this repository's tooling never writes.

No separate step remains for the canonical reader's credential: the role
projects it at apply (`reader.env` above). Until step 1's apply has run, the
observer does not exist and the incident CI job's reads refuse, which is the
safe state: an observer that is not reachable admits nothing.

## What the role asserts and never provisions

- The three secret environment variables and `BEADS_DOLT_PASSWORD` on the
  control node (step 1).
- A declared `incident_observer_candidate_user` for the host.
- The host's `tailscale serve` mapping is converged by the `tailscale_serve`
  role from the same `host_vars`, not here; `dev-host.yml` runs it right after
  this role so one apply brings the listener up and fronts it.
- The GitHub webhook, the repository variable and secret (steps 2–3) and the
  tailnet policy's `funnel` grant are named, never faked as checks.

# `fabro_server` host variables

The per-host and per-instance values this role needs, transcribed from
`fabro-hosts` `services/fabro-server/hosts/*.env` and reconciled against the
live hosts on 2026-09-09. **These are not merged into the inventory yet** —
this file exists so the role can be reviewed without touching
`ansible/inventory/legacy.yml`, which another agent owns. Merge each block
below into that host's `host_vars` entry.

The four instances here are the four `hosts/*.env` files: two hosts, two
instances each. Nothing else in the role needs configuring.

## Targeting

`hp-xubuntu` is in the inventory's `sandbox_hosts` group and `vps` is in
`dev_hosts`, so a playbook that installs every Fabro instance has to name both
groups (`hosts: dev_hosts:sandbox_hosts`) or the inventory needs a group that
holds exactly these two. That is an inventory decision, not a role one.

Note that `vps`'s inventory name is its **tailnet label**; its kernel hostname
is `vmi3006760`. The shell installer had to know both, because it compared the
values file's canonical host against `hostname -s` and against
`tailscale status --self --json`. No task in this role reads either name: the
values reach the right host because they are that host's `host_vars`.

## The playbook

The role installs one instance per invocation, so the play loops it:

```yaml
---
- name: Install the Fabro dark-factory servers
  hosts: dev_hosts:sandbox_hosts
  gather_facts: true
  tasks:
    - name: Install every Fabro instance on this host
      ansible.builtin.include_role:
        name: fabro_server
      loop: "{{ fabro_server_instances }}"
      loop_control:
        loop_var: fabro_server_instance
        label: "{{ fabro_server_instance.unit_name }}"
```

`include_role` rather than a `roles:` entry, because the role has to run once
per instance and a `roles:` entry runs once per host.

## `host_vars/hp-xubuntu.yml`

```yaml
# The service account is cwoolley, NOT ubuntu: the tailnet ACL rejects the
# ubuntu account on this host, and the checkout root is under $HOME rather
# than /data/projects.
fabro_server_host_user: cwoolley
fabro_server_host_group: cwoolley
fabro_server_host_home: /home/cwoolley
fabro_server_host_checkout: /home/cwoolley/repos/livespec-orchestrator-beads-fabro

fabro_server_instances:
  - unit_name: fabro-server
    home_dir: /home/cwoolley/.fabro
    port: 32276
    canonical_host: hp-xubuntu.perch-rudd.ts.net:32276
    cli_target_url: http://127.0.0.1:32276
    # 15 = the core count minus one, reserved for the server, janitor steps
    # and host overhead. A maintainer instruction of 2026-08-21, not a copy of
    # vps's 10: hp earns a higher over-subscription factor (3.75x against
    # vps's 2.2x) by being a dedicated factory host at load 1.36, where vps is
    # a shared box carrying dozens of user sessions.
    max_concurrent_runs: 15
    github_app_id: "3668528"
    # Live on the host since 2026-08-21.
    otel_dropin: present

  - unit_name: fabro-server-mi-homelab
    home_dir: /home/cwoolley/.fabro-mi-homelab
    port: 32277
    canonical_host: hp-xubuntu.perch-rudd.ts.net:32277
    cli_target_url: http://127.0.0.1:32277
    # A chosen value, not an observation: the host's 16 cores are already
    # over-subscribed by the fleet instance's 15, and the org factory serves
    # one repository. Raise it deliberately, with the fleet instance's number
    # in view, never by copying the entry above.
    max_concurrent_runs: 5
    github_app_id: "4688510"
    # Live on the host since 2026-08-22.
    otel_dropin: present
```

## `host_vars/vps.yml`

```yaml
fabro_server_host_user: ubuntu
fabro_server_host_group: ubuntu
fabro_server_host_home: /home/ubuntu
fabro_server_host_checkout: /data/projects/livespec-orchestrator-beads-fabro

fabro_server_instances:
  - unit_name: fabro-server
    home_dir: /home/ubuntu/.fabro
    port: 32276
    canonical_host: vps.perch-rudd.ts.net:32276
    cli_target_url: http://127.0.0.1:32276
    # vps sets this explicitly in its live, hand-maintained settings.toml.
    max_concurrent_runs: 10
    github_app_id: "3668528"
    # THE OPEN DECISION, and it is now exactly this one line. Measured
    # 2026-09-09: this is the only one of the four instances with no OTLP
    # drop-in on disk. fabro-hosts' README asks for the call to be made
    # deliberately, because installing the drop-in here newly adds OTLP export
    # from the fleet's fallback factory — a behaviour change, not a
    # transcription. `unmanaged` leaves the host as it is and says so in the
    # run output. Setting `present` turns export on; `absent` decides against
    # it. Do not leave it undecided indefinitely; do not decide it by default.
    otel_dropin: unmanaged

  - unit_name: fabro-server-mi-homelab
    home_dir: /home/ubuntu/.fabro-mi-homelab
    port: 32277
    canonical_host: vps.perch-rudd.ts.net:32277
    cli_target_url: http://127.0.0.1:32277
    # Chosen, not observed: vps is a shared box already carrying the fleet
    # instance's 10, and the org factory is the fallback, not the default.
    max_concurrent_runs: 3
    github_app_id: "4688510"
    # Live on the host since 2026-08-23.
    otel_dropin: present
```

## Values the role defaults rather than reading from `host_vars`

`fabro_server_web_verify_attempts` defaults to 300, which is what all four
values files set. It is a per-host variable if a host ever needs a different
budget; see the defaults file for why the default is 300 and not the
verifier's own 60.

`fabro_server_restart_allowed`, `fabro_server_manage_settings` and
`fabro_server_settings_mode` are deliberately not host variables. The first
two are per-run decisions an operator makes with `-e`, not standing
configuration; making either a committed host variable would turn a
deliberate act into a default.

## The `ansible_managed` banner

`templates/fabro-server.service.j2` carries `# {{ ansible_managed }}` as its
first line. `templates/settings.toml.j2` deliberately does **not**, and neither
do `files/otel.conf` or `files/fabro-server-verify-web`.

The unit is a file this role genuinely owns and rewrites on every run, so
stamping it is honest and useful — this whole repository exists because
hand-edited copies of these files drifted invisibly. `settings.toml` is the
opposite: by default the role only reports drift and never writes it, so a
banner claiming Ansible manages the file would be false in the default case
and true only under an opt-in flag. The two `files/` copies are byte-fidelity
artifacts shared with the shell installer and are copied, not templated, so
they could not carry it anyway.

The measured cost of the banner is exactly one line, and the dry run isolates
it: on the two `fabro-server-mi-homelab` instances, which the shell renderer
installed on 2026-08-23, the entire reported unit diff is `+# Ansible managed`
and nothing else. Without the banner those two instances report a zero diff.

## What the first run will report

Measured, not predicted: the role was run against **both** live hosts with
`--check --diff` on 2026-09-09 through the real `inventory/legacy.yml`.

| Host | Result |
|---|---|
| `hp-xubuntu` | ok=56 changed=3 failed=0 |
| `vps` | ok=55 changed=4 failed=0 |

Every one of those seven changes is listed below and every one is drift the
role finds rather than drift it introduces.

### `vps` / `fabro-server` — the pre-parameterization unit (2 changes)

Its installed unit predates the whole template. The render adds the
`Description` instance suffix, `FABRO_WEB_VERIFY_ATTEMPTS=300`,
`FABRO_CANONICAL_HOST`, `FABRO_BASE_URL`, the explicit `--storage-dir` and
`--config`, and the banner. The second change removes the hand-made
`verify-timeout-override.conf` drop-in, which is where that host's 300
currently lives; the resulting value is the same 300, now in the unit where a
rebuild cannot lose it.

### `hp-xubuntu` / `fabro-server` — three lines and a mode (2 changes)

The unit differs by exactly the three lines `fabro-hosts` recorded on
2026-08-23 — `Description` suffix, `FABRO_BASE_URL`, and the explicit
`--storage-dir` / `--config` — plus the banner. It already carries
`FABRO_WEB_VERIFY_ATTEMPTS` and `FABRO_CANONICAL_HOST`. Its `settings.toml`
content is **byte-identical** to the render; the only difference is mode 0644
against the role's 0600.

### Both `fabro-server-mi-homelab` instances — the banner only (2 changes)

One line each, `+# Ansible managed`. Nothing else. These were installed by the
shell renderer on 2026-08-23 and this role reproduces their unit, drop-in and
`settings.toml` byte for byte, which is the transcription's own proof.

### `vps` / `fabro-server` `settings.toml` — comments only, and this is the one to read carefully (1 change)

**The hand-maintained `max_concurrent_runs = 10` is untouched.** The reported
diff is three comment blocks and nothing else: every value line matches. That
file is the fleet's fallback factory's real configuration and overwriting its
deliberate 10 would be a regression, so the fact that the diff contains no
value line is the result worth checking on every future run. The role does not
write it in any case — the reporting task is pinned to check mode
independently of the command line.

The comments come from `settings.toml.in`, which `render-settings.sh`
preserved and this template preserves too. `fabro-hosts` recorded this render
as "identical, comments stripped"; the dry run is that same finding with the
comments left in.

Note that a mode change is not visible in Ansible's diff text, which shows
content only. The contrast between the two hosts demonstrates it: `hp` has no
content difference so its mode diff is all that prints, while `vps` has a
content difference so its mode is folded into the same reported change without
appearing.

## Out-of-band state the role asserts on and never creates

Per instance, unless noted:

1. The built Fabro binary at `<host_home>/.fabro/bin/fabro`, **shared by
   every instance on the host**.
2. `<home_dir>/storage/server.env`, mode 0600, carrying a generated
   `SESSION_SECRET` and `FABRO_DEV_TOKEN`. Fabro generates it.
3. The GitHub App private key in that instance's own Fabro vault:
   `FABRO_SERVER=http://127.0.0.1:<port> fabro secret set
   GITHUB_APP_PRIVATE_KEY --value-stdin`.
4. A `tailscale serve` mapping for the port, which lives in the
   `tailscale-admin` repository. The role cannot see it at all — see the note
   in `tasks/main.yml`.
5. `<home_dir>/settings.toml`, unless `fabro_server_manage_settings` is set.

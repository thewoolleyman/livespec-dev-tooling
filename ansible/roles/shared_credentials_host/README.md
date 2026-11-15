# `shared_credentials_host` — homelab's shared-credentials tool on the k3s CI server

livespec-dev-tooling-xyi5vu. This role installs the ADOPTER composition of
homelab's shared-credentials tool on the pool's k3s server, so the livespec-ai
ARC scale sets can take their GitHub App credentials from homelab-gitops
Parameter Store through the sealed host bootstrap identity instead of a
hand-seeded credstore.

## What a converge installs

| path | owner, mode | source |
| --- | --- | --- |
| `/usr/local/aws-cli/v2/2.34.63/dist/aws` (+ `/usr/local/bin/aws` link) | root, installer | AWS CLI v2 zip, sha256-pinned in defaults; skipped when present |
| `/usr/local/libexec/shared-credentials/shared-credentials-0.3.0.pyz` | `root:root 0755` | homelab release `shared-credentials-v0.3.0`, staged on the controller |
| `/etc/livespec-ci-credentials/<host>.json` | `root:root 0644` | `files/<host>.json` (runtime manifest) |
| `/etc/livespec-ci-credentials/<host>.delivery.json` | `root:root 0644` | `files/<host>.delivery.json` (delivery profile) |

Each installed file is read back against its sha256 pin, every directory the
tool's path-trust walk crosses is read back as root-owned and not group- or
world-writable, and the installed manifest is validated by the pinned sealer's
own `shared_credentials.manifest.load_manifest`. `/etc/credstore.encrypted` is
asserted to exist as a root-owned directory with no group or other bits; the
role never creates or changes it. It installs NO sudoers rule, user, systemd
unit or injector: livespec-dev-tooling-h5r75q owns those.

### The controller-staged sealer release

The converge stages the sealer on the CONTROLLER, into the gitignored repo-root
`tmp/shared-credentials-host/`, with
`gh release download shared-credentials-v0.3.0 --repo mi-homelab/homelab --pattern shared-credentials-0.3.0.pyz`
when it is not already there, then refuses unless its sha256 is
`a27b1f79…5918` before copying it anywhere. A bad download is repaired by
deleting the staged file and re-running.

## The consumer interface

- consumer `livespec-ai-arc`, child environment
  `LIVESPEC_AI_ARC_APP_ID`, `LIVESPEC_AI_ARC_INSTALLATION_ID`,
  `LIVESPEC_AI_ARC_PRIVATE_KEY` (homelab consumers `livespec-ai-arc-*`, read
  through `role/poweredge-xubuntu-reader`);
- launch argv:
  `sudo -n /usr/bin/python3 -I /usr/local/libexec/shared-credentials/shared-credentials-0.3.0.pyz launch --manifest /etc/livespec-ci-credentials/poweredge-xubuntu.json --consumer livespec-ai-arc -- <injector>`.

## The single initial key delivery (`tasks/mint.yml`)

The host's bootstrap user (`bootstrap_identity.user_arn` in the committed
manifest) gets exactly one access key, issued and sealed on the host by
homelab's own `infra/shared-credentials/deliver-initial-key.sh` at the commit
`files/homelab-delivery.pin` names. That commit carries the user's
`docs/credential-exception-register.md` row (mi-homelab/homelab#1215, merged).
The route is imported behind `shared_credentials_host_mint_bootstrap_key`
(default `false`) AND the `never` tag plus its own `poweredge_bootstrap_mint`
tag. The `never` tag keeps it out of every untagged converge and drift report;
the role's own tag `shared_credentials_host` is inherited by the imported tasks,
so `--tags shared_credentials_host` LISTS them, and there the boolean is what
skips every one (measured with `--list-tasks`).

Run it from the vps control node, under the homelab-mgmt issuer wrapper, `--check`
first:

```bash
cd ~/workspace/livespec-dev-tooling
/usr/local/bin/with-homelab-aws.sh --role homelab-mgmt \
  env ANSIBLE_CONFIG=ansible/ansible.cfg just ansible-drift ansible/ci-pool.yml --limit poweredge-xubuntu \
  --tags poweredge_bootstrap_mint -e shared_credentials_host_mint_bootstrap_key=true
/usr/local/bin/with-homelab-aws.sh --role homelab-mgmt \
  env ANSIBLE_CONFIG=ansible/ansible.cfg just ansible-apply ansible/ci-pool.yml --limit poweredge-xubuntu \
  --tags poweredge_bootstrap_mint -e shared_credentials_host_mint_bootstrap_key=true
```

`ANSIBLE_CONFIG` is load-bearing (set inside the wrapper, through `env`, so a wrapper
that scrubs its caller's environment cannot drop it): `just ansible-*` runs from the repository root,
where Ansible does not read `ansible/ansible.cfg` (measured 2026-11-15:
`ansible-config dump` from the root reports `CONFIG_FILE() = None`), so ssh
pipelining would be OFF and the route refuses.

Before anything is issued it refuses unless: the pin is an exact commit and the
committed manifest names this host and account; the issuer session
(`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`/`AWS_SESSION_TOKEN`) is in the
controller environment; pipelining is on and `keep_remote_files` off; the pinned
commit registers the bootstrap user exactly once; homelab's declared interpreter
(`python<.python-version>`) is on root's PATH on the target; the seal file does
not exist; the installed profile and manifest are their pinned bytes; and a
metadata-only readback from the controller shows the bootstrap user holds ZERO
access keys. It then stages the pinned commit as a root-only archive under
`/root/shared-credentials-bootstrap-mint/<commit>`, runs the delivery script as
root with the issuer session passed ONLY on its stdin (`no_log`), keeps the
receipt and stderr root-only `0600`, refuses unless the script exited 0 and the
receipt says `value_in_output: false`, and finally reads back, masked, exactly
one Active key.

### Run order

1. mi-homelab/homelab#1215 merged (done; pinned at `846ea917`).
2. Converge: `just ansible-apply ansible/ci-pool.yml --limit poweredge-xubuntu --tags shared_credentials_host`
   (drift first).
3. The mint `--check` above.
4. The mint itself, once, by legacy-dispatcher-agent.

### Known blocker at the current pin

homelab's `deliver-initial-key.sh` (since homelab #1203) execs
`python$(cat .python-version)` = `python3.13` from PATH. Measured 2026-11-15
read-only on poweredge-xubuntu (Ubuntu 26.04): `/usr/bin/python3` is 3.14, and
there is no `python3.13` on PATH or in apt. The mint's interpreter gate refuses
before any key exists until either homelab admits the host's interpreter or the
host carries a `python3.13`; this role deliberately installs no interpreter.

# restic_backup -- per-host values for the inventory

None. `restic_backup_host_tag` is this machine's inventory name and is rendered
from `inventory_hostname`; nothing else in the role is a property of one
machine. This file records what the role needs from outside it.

## Out-of-band, not provisioned here

Every input in this list is asserted before the role's first changed task, so an
apply on a host missing one fails at that assert and names it.

- `/usr/local/bin/with-homelab-env.sh`, from the `1password-env-wrapper` repo.
  The runner re-execs through it to load the repository credentials.
- The six `VPS_RESTIC_*` names in the 1Password `homelab` Environment:
  `VPS_RESTIC_REPOSITORY`, `VPS_RESTIC_PASSWORD`, `VPS_RESTIC_AWS_ACCESS_KEY_ID`,
  `VPS_RESTIC_AWS_SECRET_ACCESS_KEY`, `VPS_RESTIC_S3_BUCKET` and
  `VPS_RESTIC_S3_REGION`. A human creates the S3 bucket, the IAM user and the
  restic password once and imports them into that Environment; the role never
  reads or writes a secret. It asks the wrapper which names resolve and lists
  every one that does not.

### Fleet prerequisite the role does not read

`/usr/local/bin/with-homelab-aws.sh` and `/etc/credstore.encrypted/homelab-aws-bootstrap`
are fleet-level host glue for AWS access. No role in `ansible/` installs or
references them, and neither does this one: the runner takes its AWS keys from
the `VPS_RESTIC_AWS_*` names above, through `with-homelab-env.sh`. They are
recorded here, beside the role that handles AWS credentials, so a rebuilt host
does not lose them silently. The `homelab` repository's reconcile timer was
recorded as their owner on 2026-09-09; whether it still installs them was not
re-traced, so confirm both exist before relying on any tool that needs AWS
access through them.

### Post-apply steps an operator still performs

The role installs the runner and arms the timer, and it never runs a backup.

1. **`restic doctor`, once, after the first apply on a host.** Run
   `sudo /usr/local/sbin/vps-restic-backup doctor`. It confirms the credentials,
   the exclude file and that the repository is reachable and initialized; the
   role cannot check the last of those.
2. **The first backup, once, after `doctor` reports OK.** Start the service once
   with `sudo systemctl start vps-restic-backup.service` and watch it with
   `journalctl -u vps-restic-backup.service`. Until it has run, the timer's first
   scheduled run at 03:30 or 15:30 is the first test of a real backup. It can
   take hours, so the unit's start timeout is `restic_backup_timeout_start_sec`.

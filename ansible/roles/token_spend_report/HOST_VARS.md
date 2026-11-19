# `token_spend_report` — pinned vps token-spend scripts

This role has no per-host values. It runs only from `ansible/dev-host.yml` on
the `dev_hosts` inventory group, whose present member is the vps.

The scripts are NOT stored in this repository: its Python gates reject them as
written. Their source is `services/token-spend-report/` in the private
`vps-info` repository, pinned in `defaults/main.yml` by commit sha
(`token_spend_report_source_sha`) and by one SHA-256 per file
(`token_spend_report_scripts`). An apply:

1. extracts those files with `git archive` at the pinned commit from the
   control node's clone (`token_spend_report_source_checkout`, default
   `~/workspace/vps-info`), which must hold the commit (`git fetch` it first);
2. refuses unless each extracted file equals its pinned SHA-256;
3. copies the verified bytes to `/home/ubuntu/token-spend-report/scripts` as
   `ubuntu`, then reads every target back and refuses unless its SHA-256 equals
   the pin;
4. installs the oneshot user unit `token-spend-quota-triggers.service` (no
   `[Install]` section, no timer) and starts it only when `quota_triggers.py`,
   `build_triggers.py` or `emit_spend_key.py` changed in this apply, or the unit
   itself changed. The unit PUTs the Honeycomb triggers (idempotent by trigger
   name) through `/usr/local/bin/with-livespec-env.sh`, which supplies
   `HONEYCOMB_CONFIG_KEY_LIVESPEC`; the key is never in the unit or this repo;
5. reads the live triggers back with `quota_triggers_check.py` (GET only) and
   fails the play on any missing or differing trigger. Steps 4 and 5 are skipped
   in check mode, so `just ansible-drift` never PUTs.

An unchanged re-apply does not start the unit. If the unit failed after the
scripts were installed, the next apply sees no change and does not retry it, but
step 5 fails on the live difference: start it by hand with
`systemctl --user start token-spend-quota-triggers.service` and read
`journalctl --user -u token-spend-quota-triggers.service`.
Revert: remove the unit file and restore the previous pin. Triggers already PUT
stay in Honeycomb unchanged.

To change a script: change it in `vps-info`, merge, read the new commit sha on
origin, then bump the sha and the affected digests here in one PR. Do not edit a
script in `~/token-spend-report/scripts` by hand: the next committed apply
overwrites it. Revert by restoring the previous pin.

```bash
just ansible-drift ansible/dev-host.yml --tags token_spend_report
just ansible-apply ansible/dev-host.yml --tags token_spend_report
```

The scripts import sibling modules that are not part of this role and stay as
they are on the vps (`prices`, `accounts`, `node_join`,
`caam_source`, `codex_idle`, `journal_slots`, `tenant_usage_read`).
`emit_spend_key` was one of them until livespec-dev-tooling-caejh2 pinned it, because `build_triggers.py` imports it.

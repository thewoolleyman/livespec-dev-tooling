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
   the pin.

To change a script: change it in `vps-info`, merge, read the new commit sha on
origin, then bump the sha and the affected digests here in one PR. Do not edit a
script in `~/token-spend-report/scripts` by hand: the next committed apply
overwrites it. Revert by restoring the previous pin.

```bash
just ansible-drift ansible/dev-host.yml --tags token_spend_report
just ansible-apply ansible/dev-host.yml --tags token_spend_report
```

The scripts import sibling modules that are not part of this role and stay as
they are on the vps (`prices`, `accounts`, `node_join`, `emit_spend_key`,
`caam_source`, `codex_idle`, `journal_slots`, `tenant_usage_read`).

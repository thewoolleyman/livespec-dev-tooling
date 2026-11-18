# `token_spend_report` — committed vps token-spend scripts

This role has no per-host values. It runs only from `ansible/dev-host.yml` on
the `dev_hosts` inventory group, whose present member is the vps.

The source of every installed script is this role's committed `files/`
directory. An explicit apply copies those files to
`/home/ubuntu/token-spend-report/scripts` as `ubuntu`, then reads every target
back with SHA-256 and refuses unless it equals the source byte-for-byte. The
read-back is the host-captured proof to record after a merged apply.

Run the normal committed-source route:

```bash
just ansible-drift ansible/dev-host.yml --tags token_spend_report
just ansible-apply ansible/dev-host.yml --tags token_spend_report
```

Do not repair a script in `~/token-spend-report/scripts` by hand: that edit is
outside review and the next committed apply overwrites it. Revert by restoring
the previous committed script bytes and applying this role again.

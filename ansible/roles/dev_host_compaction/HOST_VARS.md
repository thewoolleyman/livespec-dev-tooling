# dev_host_compaction — host variables

This role manages the dev VPS's persistent policy for proactive memory
compaction. It is included by `ansible/dev-host.yml`; use its tag when the
policy alone needs a drift report or apply:

```bash
just ansible-drift ansible/dev-host.yml --tags dev_host_compaction
just ansible-apply ansible/dev-host.yml --tags dev_host_compaction
```

The role exposes no per-host tuning variable. Its defaults name the managed
`/etc/sysctl.d/90-dev-host-disable-proactive-compaction.conf` path and the
`/usr/sbin/sysctl` executable so the integration test can redirect both into
its temporary synthetic host. The committed drop-in is the one policy value:
`vm.compaction_proactiveness = 0`.

It disables only proactive compaction. On-demand compaction at watermark
pressure and direct compaction remain unchanged.

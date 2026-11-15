# shared_credentials_host -- per-host values for the inventory

The role is server-only: `ci-pool.yml` gates it on `cluster_role == 'server'`.
Everything except the two pins below is a role default. The committed inputs
themselves are `files/<inventory_hostname>.json` (the sealer's runtime manifest)
and `files/<inventory_hostname>.delivery.json` (homelab's initial-delivery
profile). Their sha256 pins vary by host, and no role value may name a machine
(`check-ansible-hostname-free`), so the pins live here.

| variable | default | where set | meaning |
| --- | --- | --- | --- |
| `shared_credentials_host_manifest_sha256` | `""` (refused) | host_vars | sha256 of `files/<host>.json` |
| `shared_credentials_host_profile_sha256` | `""` (refused) | host_vars | sha256 of `files/<host>.delivery.json` |

```yaml
# poweredge-xubuntu
shared_credentials_host_manifest_sha256: acf8fdd6d561b8ca1d5671a3764688e755d6cfd6dde2b264ebdd24abc0334f99
shared_credentials_host_profile_sha256: 56096ba3f9980f215140ad5ff95d9e3492eeb469d136faa0f7b8ef7982d860d1
```

The delivery profile's own `sealer.manifest_sha256` pins the manifest too, so a
manifest change is a change to three lines: the manifest, the profile's
`manifest_sha256`, and both pins above.

## Out-of-band, not provisioned here

The sudoers grant, the systemd unit and the injector that LAUNCH the sealer for
the `livespec-ai-arc` consumer are livespec-dev-tooling-h5r75q's. The seal
`/etc/credstore.encrypted/<host>-aws-bootstrap.cred` is written once by the
initial key delivery in `README.md`, never by a converge.

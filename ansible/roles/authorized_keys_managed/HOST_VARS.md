# `authorized_keys_managed` — narrow entries in a shared authorized_keys file

This role manages only its own marker-delimited entries and explicitly retired
public-key blobs. It leaves every other line unchanged and in place.

```yaml
authorized_keys_managed_user: ubuntu
authorized_keys_managed_group: ubuntu
authorized_keys_managed_path: /home/ubuntu/.ssh/authorized_keys
authorized_keys_managed_entries:
  - name: hetzner-xubuntu-dolt-tunnel
    public_key: ssh-ed25519 <base64> hetzner-xubuntu dolt-tunnel
    permitopen: 127.0.0.1:3307
authorized_keys_managed_retired_keys:
  - ssh-ed25519 <base64>
```

`authorized_keys_managed_retired_keys` contains exactly a key type and base64
body, never its options or comment. A retired blob that is also managed makes
the role refuse before it writes. Private keys are never committed.

Every managed entry is a local-forward-only key: `restrict`,
`port-forwarding`, an exact `permitopen`, `permitlisten="invalid.invalid:1"`,
and `command="/bin/false"` deny shells, commands, remote forwards, and other
destinations. Apply against the OpenSSH public address, not Tailscale SSH.

```text
just ansible-drift ansible/dev-host.yml --tags authorized_keys_managed
just ansible-apply ansible/dev-host.yml --tags authorized_keys_managed
```

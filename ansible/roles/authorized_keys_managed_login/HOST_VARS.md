# `authorized_keys_managed_login` — ordinary login keys in a Mac's authorized_keys

Sibling of `authorized_keys_managed` (which writes forward-only restricted
keys). This role writes an ordinary login key as a marker-delimited block and
leaves every line outside the markers untouched.

```yaml
authorized_keys_managed_login_user: cwoolley
authorized_keys_managed_login_group: staff
authorized_keys_managed_login_path: /Users/cwoolley/.ssh/authorized_keys
authorized_keys_managed_login_entries:
  - name: hetzner-xubuntu-session
    public_key: ssh-ed25519 <base64> ubuntu@hetzner-xubuntu
  - name: retired-example
    public_key: ssh-ed25519 <base64> retired
    state: absent
```

- The three scalar vars default to empty; the first task refuses before
  changing anything when any is empty. Private keys are never committed.
- The managed line is `no-X11-forwarding <public_key>`. The option prefix keeps
  the line from starting with the key type, so the adopt step (which deletes a
  hand-placed unmarked line starting with the same type and blob) never deletes
  the managed line, and a second apply reports changed=0.
- Rollback: set `state: absent` on the entry and re-apply (removes its block);
  once applied, delete the entry from the list. Deleting an entry without that
  step leaves its block in the file.
- No `become`: the connection is the account that owns the file.

```text
just ansible-drift ansible/authorized-keys-macs.yml
just ansible-apply ansible/authorized-keys-macs.yml
```

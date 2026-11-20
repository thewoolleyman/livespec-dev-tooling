# dev_tooling_checkout -- per-host values for the inventory

The role is OFF unless a host opts in. Merge the block below into that host's
`host_vars`. Only the vps (the control node) is switched on; hetzner-xubuntu and
gamingpc-xubuntu can opt in later by adding the same line.

```yaml
# vps
dev_tooling_checkout_enabled: true
```

Kill switch: set it `false` (or delete the line), or revert the change that added it.

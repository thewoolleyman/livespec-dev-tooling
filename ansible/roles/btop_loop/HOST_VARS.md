# `btop_loop` — host-specific values

The digest pin in `roles/btop_loop/defaults/main.yml` is a FLEET constant, not a
host fact, and belongs where it is. The one value below is a fact about this
machine.

```yaml
# vps
btop_loop_expected_hostname: vmi3006760
```

This is the KERNEL hostname, which on this node is its provider VM id and not
its tailnet label `vps`. The role asserts on it as defence in depth behind the
inventory, because the same tool is installed on three hosts from three
different repositories and each must take its copy from its own provisioner.

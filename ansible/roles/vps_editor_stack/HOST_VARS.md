# vps_editor_stack — per-host values

No host-specific values are currently required. The role's defaults describe
the VPS editor stack because `ansible/dev-host.yml` targets only the `vps` dev
host.

## Held service switch

`vps_editor_stack_enabled` is deliberately `false`. The role still installs
the VS Code package, both systemd units, nginx configuration, and service
worker, but converges both units disabled and stopped. This is the maintainer's
hold on the editor stack. Change this one boolean to `true` only when the hold
is lifted; do not use a hand `systemctl enable` or `start`, because the next
converge restores the declared state.

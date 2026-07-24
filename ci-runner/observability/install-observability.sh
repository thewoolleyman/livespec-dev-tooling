#!/usr/bin/env bash
# install-observability.sh — idempotently install the CI-runner liveness
# heartbeat + cache-prune units from THIS source tree onto the host.
#
# Run with sudo from the repo (or a worktree of it):
#   sudo ci-runner/observability/install-observability.sh
#
# Installs scripts to /usr/local/lib/ci-runner/ and units to
# /etc/systemd/system/, then daemon-reloads and enables both timers. Safe to
# re-run; re-running after editing the source is the ONLY sanctioned way to
# change the live copies (the s2t recreatability rule: live must equal
# source).
set -euo pipefail

src_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

install -o root -g root -m 0755 -d /usr/local/lib/ci-runner
install -o root -g root -m 0755 \
  "${src_dir}/ci-runner-heartbeat.sh" \
  "${src_dir}/ci-runner-cache-prune.sh" \
  /usr/local/lib/ci-runner/
install -o root -g root -m 0644 \
  "${src_dir}/ci-runner-heartbeat.service" \
  "${src_dir}/ci-runner-heartbeat.timer" \
  "${src_dir}/ci-runner-cache-prune.service" \
  "${src_dir}/ci-runner-cache-prune.timer" \
  /etc/systemd/system/

systemctl daemon-reload
systemctl enable --now ci-runner-heartbeat.timer ci-runner-cache-prune.timer

echo "installed: heartbeat + cache-prune (timers enabled)"
systemctl list-timers 'ci-runner-*' --no-pager | head -5

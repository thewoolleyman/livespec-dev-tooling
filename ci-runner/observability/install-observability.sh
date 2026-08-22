#!/usr/bin/env bash
# install-observability.sh — idempotently install the CI-runner liveness
# heartbeat unit from THIS source tree onto the host.
#
# The cache-prune units this installer also carried were deleted with the
# podman contained lane (livespec-s43svm.19): they pruned the ci-runner
# user's rootless podman container/image store, which no longer exists.
# k3s/containerd image hygiene is the cluster's own concern, not this
# installer's.
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
  /usr/local/lib/ci-runner/
install -o root -g root -m 0644 \
  "${src_dir}/ci-runner-heartbeat.service" \
  "${src_dir}/ci-runner-heartbeat.timer" \
  /etc/systemd/system/

systemctl daemon-reload
systemctl enable --now ci-runner-heartbeat.timer

echo "installed: heartbeat (timer enabled)"
systemctl list-timers 'ci-runner-*' --no-pager | head -5

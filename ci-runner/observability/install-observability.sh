#!/usr/bin/env bash
# install-observability.sh — idempotently install the CI-runner liveness
# heartbeat unit AND the Kueue-webhook endpoint-readiness probe from THIS source
# tree onto the host.
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
# The Kueue-webhook probe (ci-kueue-webhook-probe.*, livespec-s43svm.46) needs a
# scoped read-only kubeconfig this installer does NOT provision. Apply the
# committed RBAC once — `sudo k3s kubectl apply -f
# ci-runner/observability/kueue-webhook-probe-rbac.yaml` — then generate the
# kubeconfig from the populated token Secret (see that file's header) at
# ${CI_KUEUE_PROBE_KUBECONFIG:-/etc/ci-runner/kueue-webhook-probe.kubeconfig},
# root-owned mode 0600. Without it the probe fails-closed (emits nothing, exits
# nonzero) rather than reporting a false zero.
#
# DEPENDENCY: the heartbeat POSTs to a LOCAL OTel collector on
# 127.0.0.1:4319. That collector is NOT installed by this script — it is the
# CI-runner-host shape of https://github.com/thewoolleyman/otel-collector
# (scripts/install-ci-runner-host.sh there). Without it every heartbeat
# firing exits 7 (`curl: (7)`), which is exactly what happened from
# 2026-08-15 to 2026-08-23 (livespec-s43svm.20). After installing, run
# `systemctl start ci-runner-heartbeat.service` once and confirm it exits 0.
#
# Installs scripts to /usr/local/lib/ci-runner/ and units to
# /etc/systemd/system/, then daemon-reloads and enables all timers. Safe to
# re-run; re-running after editing the source is the ONLY sanctioned way to
# change the live copies (the s2t recreatability rule: live must equal
# source).
set -euo pipefail

src_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

install -o root -g root -m 0755 -d /usr/local/lib/ci-runner
install -o root -g root -m 0755 \
  "${src_dir}/ci-runner-heartbeat.sh" \
  "${src_dir}/ci-kueue-webhook-probe.sh" \
  /usr/local/lib/ci-runner/
install -o root -g root -m 0644 \
  "${src_dir}/ci-runner-heartbeat.service" \
  "${src_dir}/ci-runner-heartbeat.timer" \
  "${src_dir}/ci-kueue-webhook-probe.service" \
  "${src_dir}/ci-kueue-webhook-probe.timer" \
  /etc/systemd/system/

systemctl daemon-reload
systemctl enable --now ci-runner-heartbeat.timer
systemctl enable --now ci-kueue-webhook-probe.timer

echo "installed: heartbeat + kueue-webhook-probe (timers enabled)"
systemctl list-timers 'ci-runner-*' 'ci-kueue-*' --no-pager | head -6

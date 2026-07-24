#!/usr/bin/env bash
# ci-runner-cache-prune.sh — age-aware storage hygiene for the ci-runner
# user's rootless podman (the local CI lane's job containers and images).
#
# Runs daily from ci-runner-cache-prune.timer AS ci-runner (mirroring
# runner@.service's User=/XDG_RUNTIME_DIR pattern). Three passes:
#
#   1. Containers older than 5 days are removed even if "Up": an exited or
#      wedged job container has no legitimate reason to outlive its run by
#      days (proven live: an orphaned job container from the 2026-07-18
#      incident sat "Up 5 days"). Ephemeral JIT runners tear their own
#      containers down within minutes; the age bar only catches wreckage.
#   2. Dangling images go immediately.
#   3. Unused tagged images older than 14 days go (`image prune -a`). The
#      until filter keys on CREATION time, so a still-pinned sandbox image
#      built >14 days ago can be swept — that is accepted and self-healing:
#      the next sentinel/CI job re-pulls it once (~30 s). The disk-free
#      Honeycomb triggers (50 GB warn / 20 GiB floor) are the budget
#      backstop this prune keeps comfortably far away.
#
# Source of truth: livespec-dev-tooling ci-runner/observability/ — install
# via install-observability.sh, never hand-edit the live copy.
set -euo pipefail

echo "cache-prune: storage before:"
podman system df 2>/dev/null || true

# 1. Wreckage containers (anything older than 5 days, running or not).
stale_ids="$(podman ps --all --filter 'status=running' --format '{{.ID}} {{.CreatedAt}}' \
  | awk -v cutoff="$(date -d '5 days ago' +%s)" '{
      cmd = "date -d \"" $2 " " $3 " " $4 "\" +%s"; cmd | getline created; close(cmd);
      if (created < cutoff) print $1
    }' || true)"
if [ -n "${stale_ids}" ]; then
  echo "cache-prune: removing wedged running containers older than 5 days: ${stale_ids}"
  # shellcheck disable=SC2086
  podman rm -f ${stale_ids}
fi
podman container prune -f --filter until=120h > /dev/null

# 2 + 3. Images: dangling now; unused tagged after 14 days.
podman image prune -f > /dev/null
podman image prune -af --filter until=336h > /dev/null

echo "cache-prune: storage after:"
podman system df 2>/dev/null || true

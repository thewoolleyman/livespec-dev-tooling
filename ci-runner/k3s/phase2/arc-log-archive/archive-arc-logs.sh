#!/usr/bin/env bash
# archive-arc-logs.sh — copy ARC controller and listener logs off the container
# runtime's rotating buffer and onto disk, so a failure that is diagnosed hours
# later still has evidence.
#
# THE PROBLEM THIS SOLVES. Container logs live in the kubelet's rotating buffer,
# and the ARC controller is chatty enough to churn through it fast. Measured on
# poweredge-xubuntu 2026-08-19: `kubectl logs deploy/arc-gha-rs-controller`
# retained 07:02Z-08:13Z — about SEVENTY MINUTES, 31961 lines. Re-measured four
# minutes later it had already rotated to a four-minute window.
#
# That is shorter than the time it takes to notice a problem, let alone triage
# one. It was found the hard way (livespec-s43svm.30): a wedged runner at 03:43Z
# was investigated at ~08:00Z, and the controller log that would have said
# whether ARC deleted the runner's registration had rotated away hours earlier.
# The grep returned zero matches, and a zero from a log that does not cover the
# window is not evidence of absence — it is the absence of evidence, which is
# the more dangerous of the two because it reads the same.
#
# WHY NOT JUST RAISE THE KUBELET'S ROTATION LIMITS. That is the direct fix and
# it is deliberately NOT taken here: `--container-log-max-size` /
# `--container-log-max-files` are k3s server arguments, so changing them means
# restarting k3s — on the host that carries every fleet repository's gating CI.
# A diagnostic improvement is not worth an outage window. This runs entirely
# beside the cluster, adds no cluster object, and can be removed by disabling
# one timer. If the rotation limits are ever raised for other reasons, this
# stays correct and simply has less work to do.
#
# WHY LISTENERS TOO, WHEN THEY RETAIN LONGER. The listeners measured ~9 hours,
# which covered the incident and is why the reframing on livespec-s43svm.30 was
# possible at all. That margin is a property of their current traffic, not a
# guarantee, and the same burst that makes an incident interesting is what
# shortens it. Archiving both costs one extra loop iteration.
#
# EXACTLY-ONCE-ISH, and why the state file is per-pod. Each pod's last archived
# log timestamp is remembered, and the next run asks only for lines after it.
# Without that, every run would re-append its whole overlap window and the
# archive would be mostly duplicates — which matters more than tidiness, because
# a forensic grep that returns the same line eleven times invites the reader to
# infer a repeating event that never repeated.
#
# FAIL-SOFT, per pod. A pod that cannot be read (restarting, evicted, gone) is
# named and skipped; it never aborts the sweep over the remaining pods. Losing
# one pod's slice is a small harm, losing the whole archive run is not.
#
# Requires: kubectl and a KUBECONFIG for the k3s cluster (see ../../provision-k3s.sh).
set -euo pipefail

USAGE="usage: archive-arc-logs.sh [--namespace NS] [--archive-dir DIR] [--state-dir DIR] [--max-bytes N]"

NAMESPACE="${ARC_LOG_ARCHIVE_NAMESPACE:-arc-systems}"
ARCHIVE_DIR="${ARC_LOG_ARCHIVE_DIR:-/var/log/arc-archive}"
# Per-pod "last archived line timestamp" lives beside the other ci-runner-k3s
# runtime state, for the same reason the wedged-runner streak does: it is state
# a systemd oneshot accumulates, and /var/lib is where that belongs.
STATE_DIR="${ARC_LOG_ARCHIVE_STATE_DIR:-/var/lib/ci-runner-k3s/arc-log-archive}"
# Size ceiling per archive file before it is rolled to <name>.1. One generation
# is kept, so the horizon is roughly twice this.
#
# Sized from MEASUREMENT, not from a round number. Archiving the live cluster on
# 2026-08-19 gave 328 bytes/line, and the ARC controller emitted 576 lines in a
# ~40s window — about 860 lines/min, or 16.2 MB/hour. So:
#
#     256 MiB  ->  ~16 hours per generation
#       1 GiB  ->  ~63 hours per generation  (~5 days across both)
#
# 1 GiB is chosen because an incident found on a Monday is routinely
# investigated on a Wednesday, and a horizon shorter than that reintroduces the
# exact failure this script exists to prevent — just further out. The host has
# 279 GB free, and the listeners are an order of magnitude quieter than the
# controller, so the realistic total is a few GB rather than 11 x 2 GiB.
#
# An earlier draft of this comment claimed 256 MiB was "on the order of a week"
# from an estimated ~450 lines/min. The measurement above is roughly double that
# rate, which made the claim wrong by about a factor of ten. Recording the
# correction rather than quietly editing the number, because the lesson is that
# the estimate and the measurement disagreed in the direction that mattered.
MAX_BYTES="${ARC_LOG_ARCHIVE_MAX_BYTES:-1073741824}"

while [ $# -gt 0 ]; do
  case "$1" in
    --namespace)   NAMESPACE="${2:?$USAGE}"; shift 2 ;;
    --archive-dir) ARCHIVE_DIR="${2:?$USAGE}"; shift 2 ;;
    --state-dir)   STATE_DIR="${2:?$USAGE}"; shift 2 ;;
    --max-bytes)   MAX_BYTES="${2:?$USAGE}"; shift 2 ;;
    -h|--help)     echo "$USAGE"; exit 0 ;;
    *)             echo "FATAL: unknown argument '$1'"$'\n'"$USAGE" >&2; exit 2 ;;
  esac
done

[[ "$MAX_BYTES" =~ ^[0-9]+$ ]] || { echo "FATAL: --max-bytes must be a non-negative integer, got '${MAX_BYTES}'" >&2; exit 2; }

command -v kubectl >/dev/null || { echo "FATAL: kubectl not found on PATH" >&2; exit 2; }
: "${KUBECONFIG:?set KUBECONFIG to the k3s cluster kubeconfig (see ../../provision-k3s.sh)}"

mkdir -p "$ARCHIVE_DIR" "$STATE_DIR"

# Roll a file that has grown past the ceiling. One generation, no compression:
# the archive's whole purpose is to be greppable in a hurry during an incident,
# and a compressed generation is one `zgrep` the reader has to think of.
roll_if_large() {
  local f="$1" size
  [ -f "$f" ] || return 0
  size=$(stat -c %s "$f" 2>/dev/null || echo 0)
  if [ "$size" -ge "$MAX_BYTES" ]; then
    mv -f "$f" "${f}.1"
    echo "  rolled $(basename "$f") at ${size} bytes"
  fi
}

archived_total=0
skipped=""

# `--timestamps` prefixes every line with an RFC 3339 stamp. That is what makes
# the resume point exact rather than approximate, and it is also what makes the
# archive independently readable — a line in a file on disk carries no implicit
# "when" the way a live `kubectl logs` tail does.
for pod in $(kubectl get pods -n "$NAMESPACE" -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' 2>/dev/null); do
  [ -n "$pod" ] || continue

  state_file="${STATE_DIR}/${pod}.last"
  archive_file="${ARCHIVE_DIR}/${pod}.log"
  roll_if_large "$archive_file"

  since_args=()
  if [ -f "$state_file" ]; then
    last="$(cat "$state_file" 2>/dev/null || true)"
    # A malformed or empty state file must not silently turn into "fetch
    # everything" — that is how an archive quietly doubles. Treat it as absent
    # only when it is genuinely absent.
    if [ -n "$last" ]; then
      since_args=(--since-time="$last")
    fi
  fi

  if ! raw="$(kubectl logs -n "$NAMESPACE" "$pod" --all-containers --timestamps "${since_args[@]+"${since_args[@]}"}" 2>/dev/null)"; then
    skipped="${skipped} ${pod}"
    continue
  fi
  [ -n "$raw" ] || continue

  # `--since-time` is inclusive at the boundary, so the line whose timestamp
  # equals the stored one comes back again. Dropping it here is what keeps the
  # archive duplicate-free across runs.
  if [ -n "${last:-}" ]; then
    new="$(printf '%s\n' "$raw" | awk -v cutoff="$last" '$1 > cutoff')"
  else
    new="$raw"
  fi
  unset last
  [ -n "$new" ] || continue

  printf '%s\n' "$new" >> "$archive_file"
  printf '%s' "$(printf '%s\n' "$new" | tail -1 | awk '{print $1}')" > "$state_file"
  lines=$(printf '%s\n' "$new" | wc -l)
  archived_total=$(( archived_total + lines ))
  printf '  %-56s +%s lines\n' "$pod" "$lines"
done

[ -n "$skipped" ] && echo "  skipped (unreadable this run):${skipped}"
echo "archived ${archived_total} new lines into ${ARCHIVE_DIR}"

#!/usr/bin/env bash
# prune-gate-refs.sh — the sweep that keeps the gate mirrors' `refs/gates/*`
# namespace bounded (R4.S4, livespec-dev-tooling-2hno; plan livespec
# k3s-on-gmktec-for-vps-usage, epic livespec-sab5gn; design in that plan's
# research/003 section E).
#
# THE PROBLEM IT SOLVES. Every gated push creates one ref, named after the tree
# it gates. Nothing in the protocol ever removes it, so a mirror accumulates a
# ref per gated tree forever, and with it the objects those refs keep
# reachable. The design names two collectors and this is the second of them:
#
#   1. THE CLIENT deletes its own ref once it has a verdict. That is the
#      primary path, it is immediate, and it is the gate client's job (R4.S7,
#      livespec-dev-tooling-2u2c). It cannot be the only one: a client that
#      dies between the push and the verdict leaves its ref behind, which is
#      exactly the case where nobody is left to clean up.
#   2. THIS SWEEP removes what the client did not, on an age cutoff, from a
#      timer (./gate-ref-prune.timer) and once per converge
#      (./converge-gates-mirror.sh). One day is the default: comfortably longer
#      than any gate run, short enough that a week of abandoned pushes is not a
#      week of retained trees.
#
# HOW A REF'S AGE IS DECIDED, and why not by its commit. The obvious source —
# the commit's committer date — is WRONG here: re-gating a tree from last month
# pushes a month-old commit, and aging by that would delete the ref out from
# under a gate that is still running. What matters is when the ref was PUSHED,
# so the sweep reads, in order:
#
#   a. the timestamp of the last reflog entry for the ref
#      (`<mirror>/logs/refs/gates/<hash>`). This is the push time exactly, and
#      it survives `git pack-refs`/`git gc`, which is why it is preferred.
#      ./converge-gates-mirror.sh sets core.logAllRefUpdates on every mirror so
#      this file exists.
#   b. the mtime of the loose ref file, when there is no reflog — the case for
#      a ref written by a hand `git update-ref` in a repository with reflogs
#      off.
#
# A ref with NEITHER — a packed ref in a repository with no reflog — is
# REPORTED and left alone, never silently skipped and never guessed at. A
# sweep that quietly stopped collecting is the failure this whole script
# exists to prevent, so it must not be able to happen without saying so.
#
# OBJECTS, not just refs. Deleting a ref only makes its objects unreachable;
# `git prune` is what reclaims the disk. Its expiry is the SAME cutoff, which
# is what makes it safe against a push in flight: objects a running push has
# written but not yet referenced are seconds old, far inside the cutoff.
#
# WHY IT MAY RE-EXEC ITSELF. The mirrors are owned by the account the SSH
# receive path lands as, and git refuses to operate on a repository owned by
# another user. Rather than hardcode that account in a systemd unit — a second
# place to keep in step with ./converge-gates-mirror.sh's --owner — a root
# invocation reads the mirror root's ACTUAL owner and re-executes itself as
# that account. The directory is the single source of truth for who owns it.
#
# Exit 0 when every mirror was swept, 1 when one could not be read. Touches
# nothing outside the mirror root.
set -uo pipefail

ORIGINAL_ARGS=("$@")

MIRROR_ROOT="${GATES_MIRROR_ROOT:-/var/cache/ci-runner/gates-mirror}"
MAX_AGE_SECONDS="${GATE_REF_MAX_AGE_SECONDS:-86400}"
DRY_RUN=0
REEXEC=1

usage() {
  printf 'usage: %s [--mirror-root DIR] [--max-age-seconds N] [--dry-run]\n' "$(basename "$0")"
}
while [ "$#" -gt 0 ]; do
  case "$1" in
    --mirror-root)     MIRROR_ROOT="${2:?--mirror-root needs a directory}"; shift 2 ;;
    --max-age-seconds) MAX_AGE_SECONDS="${2:?--max-age-seconds needs a number}"; shift 2 ;;
    --dry-run)         DRY_RUN=1; shift ;;
    # Internal, set by the re-exec below so it can happen at most once.
    --no-reexec)       REEXEC=0; shift ;;
    -h|--help)         usage; exit 0 ;;
    *) printf 'FATAL: unknown argument: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

case "${MAX_AGE_SECONDS}" in
  *[!0-9]* | "") echo "FATAL: --max-age-seconds must be a whole number of seconds: ${MAX_AGE_SECONDS}" >&2; exit 2 ;;
esac
command -v git >/dev/null || { echo "FATAL: git not found on PATH" >&2; exit 1; }

if [ ! -d "${MIRROR_ROOT}" ]; then
  echo "no gate mirror root at ${MIRROR_ROOT}; nothing to sweep"
  exit 0
fi

# --- the at-most-once re-exec as the mirror's owner ---------------------------
if [ "${REEXEC}" -eq 1 ] && [ "$(id -u)" -eq 0 ]; then
  owner="$(stat -c '%U' "${MIRROR_ROOT}" 2>/dev/null || true)"
  if [ -n "${owner}" ] && [ "${owner}" != "root" ] && [ "${owner}" != "UNKNOWN" ]; then
    command -v runuser >/dev/null || {
      echo "FATAL: ${MIRROR_ROOT} is owned by ${owner} and runuser is not on PATH -- git would refuse the repositories as dubiously owned" >&2
      exit 1
    }
    echo "re-executing as ${owner}, the owner of ${MIRROR_ROOT}"
    exec runuser -u "${owner}" -- "$0" --no-reexec "${ORIGINAL_ARGS[@]}"
  fi
fi

now="$(date +%s)"
cutoff=$((now - MAX_AGE_SECONDS))
status=0
total_pruned=0
total_kept=0
total_unaged=0

echo "sweeping ${MIRROR_ROOT} for refs/gates/* older than ${MAX_AGE_SECONDS}s (pushed before epoch ${cutoff})"

# The push time of a ref, echoed as a unix timestamp, or nothing when neither
# source is available. Sources and their order are the header's (a) then (b).
ref_pushed_at() {
  local logfile="$1/logs/$2" loose="$1/$2" line
  if [ -f "${logfile}" ]; then
    # A reflog line is `<old> <new> <name> <email> <ts> <tz>\t<message>`, and
    # the name may contain spaces — so cut the message off at the tab first,
    # then take the second-to-last field, which is the timestamp whatever the
    # name looked like.
    line="$(tail -n 1 "${logfile}")"
    printf '%s' "${line%%$'\t'*}" | awk 'NF >= 2 { print $(NF - 1) }'
    return 0
  fi
  if [ -f "${loose}" ]; then
    stat -c '%Y' "${loose}"
    return 0
  fi
  return 0
}

for repo_dir in "${MIRROR_ROOT}"/*.git; do
  [ -e "${repo_dir}/HEAD" ] || continue
  if ! refs="$(git --git-dir="${repo_dir}" for-each-ref --format='%(refname)' 'refs/gates/' 2>&1)"; then
    echo "ERROR: cannot read refs in ${repo_dir}: ${refs}" >&2
    status=1
    continue
  fi
  pruned=0
  kept=0
  unaged=0
  while IFS= read -r refname; do
    [ -n "${refname}" ] || continue
    pushed_at="$(ref_pushed_at "${repo_dir}" "${refname}")"
    case "${pushed_at}" in
      *[!0-9]* | "")
        echo "WARN: ${repo_dir} ${refname}: no reflog entry and no loose ref file -- age unknown, NOT pruned. A packed ref in a repository with reflogs off; re-push it or delete it by hand." >&2
        unaged=$((unaged + 1))
        continue ;;
    esac
    if [ "${pushed_at}" -lt "${cutoff}" ]; then
      if [ "${DRY_RUN}" -eq 1 ]; then
        echo "  would delete ${repo_dir} ${refname} (pushed ${pushed_at})"
      elif ! git --git-dir="${repo_dir}" update-ref -d "${refname}"; then
        echo "ERROR: failed to delete ${refname} in ${repo_dir}" >&2
        status=1
        continue
      fi
      pruned=$((pruned + 1))
    else
      kept=$((kept + 1))
    fi
  done <<< "${refs}"

  if [ "${DRY_RUN}" -eq 1 ]; then
    echo "  would run: git --git-dir=${repo_dir} prune --expire=${MAX_AGE_SECONDS} seconds ago"
  elif ! git --git-dir="${repo_dir}" prune --expire="${MAX_AGE_SECONDS} seconds ago"; then
    echo "ERROR: git prune failed in ${repo_dir}" >&2
    status=1
  fi

  echo "  $(basename "${repo_dir}"): pruned ${pruned}, kept ${kept}, unaged ${unaged}"
  total_pruned=$((total_pruned + pruned))
  total_kept=$((total_kept + kept))
  total_unaged=$((total_unaged + unaged))
done

echo "swept ${MIRROR_ROOT}: pruned ${total_pruned}, kept ${total_kept}, unaged ${total_unaged}"
exit "${status}"

#!/bin/bash
# action-archive-entry.sh -- the runner container's entry point. It names the
# work volume's seeded action archive tree to the stock runner, then hands over
# to /home/runner/run.sh unchanged.
#
# WHY AN ENTRY POINT. The runner downloads every `uses:` action during Set up
# job, in the RUNNER process of the runner pod, BEFORE it asks the container
# hook to create the job container -- so neither the hook pod template's
# postStart (which runs later, for the job pod) can steer it.
# The one place that precedes the download is the runner's own environment, and
# a static `env:` entry cannot honour the fleet kill switch or the cold canary.
# This script is the seam: it exports ACTIONS_RUNNER_ACTION_ARCHIVE_CACHE only
# when every condition holds, and otherwise leaves it unset, so the runner
# downloads exactly as it would without the tier. The variable's value is this
# file's, never a workflow's: a workflow step runs after the download.
#
# THE CONDITIONS (all, else no variable):
#   - the hook pod template this pod mounts (ACTIONS_RUNNER_CONTAINER_HOOK_TEMPLATE,
#     the same ConfigMap the job pod's postStart reads) is
#     readable, so the switch and canary can be read at all;
#   - CI_CACHE_KILL_SWITCH in it is empty;
#   - this runner is not the canary: the job pod is named
#     <runner pod name, first 54 characters>-workflow, and the canary is the pod
#     whose POSIX cksum of that name is 0 mod CI_CACHE_CANARY_N, the rule
#     postStart applies to $HOSTNAME;
#   - the seeded tree exists in the work volume and is readable.
# An inherited ACTIONS_RUNNER_ACTION_ARCHIVE_CACHE is unset when any fails, so a
# cold job is cold. A runner whose archive is absent from the tree, or whose
# tree is unreadable, falls back to the download by itself.
set -u

ARCHIVE_DIR="${ACTION_ARCHIVE_SEED_DIR:-/home/runner/_work/_warm/actions/archives}"
RUN_SH="${RUNNER_RUN_SH:-/home/runner/run.sh}"

# template_value FILE NAME -- the `value:` of the env entry NAME in a pod
# template, by the rule postStart applies: the line after
# `name: NAME`, a "double" or 'single' quoted string, or a bare word.
template_value() {
  awk -v want="$2" '
    armed && /^[[:space:]]*$/ { next }
    armed {
      line = $0
      sub(/^[[:space:]]*/, "", line)
      if (line ~ /^value:/) {
        sub(/^value:[[:space:]]*/, "", line)
        first = substr(line, 1, 1)
        if (first == "\"" || first == "\047") {
          rest = substr(line, 2)
          close_at = index(rest, first)
          if (close_at > 0) { print substr(rest, 1, close_at - 1) }
        } else {
          match(line, /^[^[:space:]#"\047]*/)
          print substr(line, 1, RLENGTH)
        }
      }
      exit
    }
    $0 ~ ("name:[[:space:]]*" want "[[:space:]]*$") { armed = 1 }
  ' "$1"
}

tier_on=0
template="${ACTIONS_RUNNER_CONTAINER_HOOK_TEMPLATE:-}"
if [ -n "${template}" ] && [ -r "${template}" ]; then
  tier_on=1
  switch="$(template_value "${template}" CI_CACHE_KILL_SWITCH)"
  canary="$(template_value "${template}" CI_CACHE_CANARY_N)"
  runner_pod="${ACTIONS_RUNNER_POD_NAME:-}"
  if [ -n "${switch}" ]; then
    tier_on=0
  elif [[ "${canary}" =~ ^[0-9]+$ ]] && [ "$((10#${canary}))" -gt 0 ] && [ -n "${runner_pod}" ]; then
    crc="$(printf '%s' "${runner_pod:0:54}-workflow" | cksum | cut -d' ' -f1)"
    if [ $(( crc % 10#${canary} )) -eq 0 ]; then tier_on=0; fi
  fi
fi
if [ "${tier_on}" -eq 1 ] && [ -d "${ARCHIVE_DIR}" ] && [ -r "${ARCHIVE_DIR}" ] && [ -x "${ARCHIVE_DIR}" ]; then
  export ACTIONS_RUNNER_ACTION_ARCHIVE_CACHE="${ARCHIVE_DIR}"
else
  unset ACTIONS_RUNNER_ACTION_ARCHIVE_CACHE
fi
exec "${RUN_SH}" "$@"

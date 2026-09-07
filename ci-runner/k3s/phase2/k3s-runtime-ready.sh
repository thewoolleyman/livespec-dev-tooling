#!/usr/bin/env bash
# k3s-runtime-ready.sh — SOURCED by the node-local scripts in this tree (never
# run): the ONE place that says how a script waits for this node's k3s container
# runtime to be usable, and which socket "the containerd socket" names.
#
# WHY THIS EXISTS. A runbook step that talks to containerd can be reached while
# k3s is still coming up, and containerd's socket FILE exists before anything is
# listening on it — so the failure is `connect: connection refused`, not "no such
# file". Measured on gmktec-xubuntu 2026-09-07 (livespec-dev-tooling-4qp4):
# ../install-node.sh step 1 replaced that agent's k3s config while
# k3s-agent.service was restart-looping, the unit came up five seconds later, and
# step 7c ran first — container-hook/extract-externals.sh died at its first
# `ctr images pull` with
#   ctr: connection error: dial unix /run/k3s/containerd/containerd.sock:
#   connect: connection refused
# A second identical invocation minutes later succeeded, which is the shape this
# file removes: a recipe that needs to be run twice is not a recipe.
#
# THE PROBE IS A CALL, NOT A STAT. Because the refused connect happens on a
# socket that already exists, `[ -S ... ]` would report a runtime that is up when
# it is not. The readiness test is therefore a trivial containerd RPC —
# `ctr version`, which asks the daemon for its server version and fails while
# nothing is listening.
#
# ON A SERVER NOTHING HERE CHANGES. ../provision-k3s.sh already waits for the
# node to go Ready before it reaches the runbook, and no step of a server run
# restarts k3s; the agent path has neither of those, which is why the waits are
# reached from the agent side.
#
# Expects nothing of the caller. Every function prints its progress on stdout,
# returns 0 on readiness and non-zero on timeout, and leaves the FATAL wording to
# the caller so each script names the step the operator was in.

# The address `ctr` will dial. k3s's containerd listens here, and containerd's
# own CONTAINERD_ADDRESS environment variable is honoured so the wait and the
# calls after it can never be aimed at two different sockets.
K3S_RUNTIME_CONTAINERD_SOCKET="${CONTAINERD_ADDRESS:-/run/k3s/containerd/containerd.sock}"

# The bound and the cadence. 120 s is the outer bound because a k3s (re)start on
# this hardware reaches a serving containerd in single-digit seconds and the
# measured case above needed five; 2 s between probes is short enough that a
# ready runtime costs the runbook nothing, and one progress line per 10 s is what
# keeps a wait from reading as a hang.
# shellcheck disable=SC2034  # read by the scripts that source this file
K3S_RUNTIME_WAIT_SECONDS=120
K3S_RUNTIME_POLL_SECONDS=2
K3S_RUNTIME_REPORT_SECONDS=10

# k3s_ctr_command -> the argv for containerd's ctr on this node, one word per
# line, or NOTHING when neither form is present. k3s installs a `ctr` symlink
# pointed at its own socket; the `k3s ctr` subcommand is the same client when the
# symlink is absent. Read here rather than in each caller so the client the wait
# probes with is the client the work after it uses.
k3s_ctr_command() {
  if command -v ctr >/dev/null 2>&1; then
    printf 'ctr\n'
  elif command -v k3s >/dev/null 2>&1; then
    printf 'k3s\nctr\n'
  fi
}

# k3s_runtime_wait_plan_line SECONDS -> the one-line description of the wait,
# for a --dry-run plan. Composed HERE so a plan cannot describe a bound, a
# cadence or a socket that differs from the one the run would use.
k3s_runtime_wait_plan_line() {
  printf 'wait up to %ss (probing every %ss) for containerd at %s to answer `ctr version`' \
    "$1" "${K3S_RUNTIME_POLL_SECONDS}" "${K3S_RUNTIME_CONTAINERD_SOCKET}"
}

# wait_for_containerd SECONDS PROBE... -> 0 once PROBE succeeds, 1 on timeout.
# PROBE is run with its output discarded; it is the caller's `ctr version`.
wait_for_containerd() {
  local budget="$1"; shift
  local waited=0
  while ! "$@" >/dev/null 2>&1; do
    if [ "${waited}" -ge "${budget}" ]; then
      return 1
    fi
    sleep "${K3S_RUNTIME_POLL_SECONDS}"
    waited=$((waited + K3S_RUNTIME_POLL_SECONDS))
    if [ $((waited % K3S_RUNTIME_REPORT_SECONDS)) -eq 0 ]; then
      printf 'still waiting for containerd at %s (%ss of %ss)\n' \
        "${K3S_RUNTIME_CONTAINERD_SOCKET}" "${waited}" "${budget}"
    fi
  done
  printf 'containerd at %s answered `ctr version` after %ss\n' \
    "${K3S_RUNTIME_CONTAINERD_SOCKET}" "${waited}"
}

# wait_for_unit_active UNIT SECONDS -> 0 once systemd reports UNIT active, 1 on
# timeout. A restart-looping unit reports `activating` between attempts, which is
# exactly the state the measured failure was in, so anything but `active` waits.
wait_for_unit_active() {
  local unit="$1" budget="$2" waited=0
  while ! systemctl is-active --quiet "${unit}" 2>/dev/null; do
    if [ "${waited}" -ge "${budget}" ]; then
      return 1
    fi
    sleep "${K3S_RUNTIME_POLL_SECONDS}"
    waited=$((waited + K3S_RUNTIME_POLL_SECONDS))
    if [ $((waited % K3S_RUNTIME_REPORT_SECONDS)) -eq 0 ]; then
      printf 'still waiting for %s to be active (%ss of %ss)\n' "${unit}" "${waited}" "${budget}"
    fi
  done
  printf '%s is active after %ss\n' "${unit}" "${waited}"
}

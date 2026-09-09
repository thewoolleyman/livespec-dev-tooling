#!/usr/bin/env bash
# gha-runner-run.sh -- ExecStart for gha-runner.service. Runs INSIDE the
# credential wrapper (the unit's ExecStart is `<wrapper> -- this script`), so
# the livespec 1Password Environment's operator secrets are already in this
# process's environment and are inherited by every job the runner executes.
#
# WHY A LAUNCHER RATHER THAN ExecStart=<wrapper> -- <runner>/run.sh: the wrapper
# deliberately scrubs the environment (`env -i`) and hard-codes PATH to the
# system secure_path. On this fleet that PATH has no `fabro` on it, so a job
# would fail at its first orchestrator call with exit 127 -- and would do so
# only at job time, far from the unit that caused it. The unit's
# `Environment=PATH=` cannot fix that either: the wrapper's scrub runs AFTER
# systemd has set it. So PATH is re-established HERE, from the installed host
# values file, which is the same file the installer rendered the unit from.
#
# This script is deliberately the only place that knows the runner's entry
# point. It execs, so the runner -- not this shell -- is what the cgroup's stop
# signal reaches last.
set -euo pipefail

ENV_FILE="${GHA_RUNNER_ENV_FILE:-/usr/local/libexec/gha-runner.env}"

[[ -r "${ENV_FILE}" ]] || {
    echo "ERROR: cannot read installed host values: ${ENV_FILE}" >&2
    echo "       Re-run: just ansible-apply ansible/fabro-hosts.yml --limit <host> --tags gha_runner" >&2
    exit 2; }
# shellcheck source=/dev/null
source "${ENV_FILE}"

: "${GHA_RUNNER_DIR:?${ENV_FILE} must set GHA_RUNNER_DIR}"
: "${GHA_RUNNER_HOME:?${ENV_FILE} must set GHA_RUNNER_HOME}"
: "${GHA_RUNNER_JOB_PATH:?${ENV_FILE} must set GHA_RUNNER_JOB_PATH}"

export HOME="${GHA_RUNNER_HOME}"
export PATH="${GHA_RUNNER_JOB_PATH}"

[[ -x "${GHA_RUNNER_DIR}/run.sh" ]] || {
    echo "ERROR: runner release is not unpacked at ${GHA_RUNNER_DIR}/run.sh" >&2
    echo "       Re-run: just ansible-apply ansible/fabro-hosts.yml --limit <host> --tags gha_runner" >&2
    exit 3; }

# .runner is written by config.sh and is the ONLY on-disk evidence that this
# runner is registered. Without it run.sh starts, fails to authenticate and
# exits, and `Restart=always` turns that into a loop whose journal says nothing
# about the actual cause. Refusing here names the cause once.
[[ -f "${GHA_RUNNER_DIR}/.runner" ]] || {
    echo "ERROR: ${GHA_RUNNER_DIR} is not configured (.runner is absent)" >&2
    echo "       Register it: just ansible-apply ansible/fabro-hosts.yml --limit <host> --tags gha_runner" >&2
    exit 4; }

cd "${GHA_RUNNER_DIR}"
exec ./run.sh

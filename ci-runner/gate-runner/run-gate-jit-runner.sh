#!/usr/bin/env bash
# run-gate-jit-runner.sh — ExecStart for gate-runner@.service. Reads the one-shot
# JIT config systemd staged via LoadCredential (readable only under this unit's
# $CREDENTIALS_DIRECTORY) and execs the runner for a single ephemeral job, after
# which it auto-deregisters and the host again has NO privileged runner.
set -euo pipefail
jit="$(cat "${CREDENTIALS_DIRECTORY}/jit")"
exec /home/ubuntu/gate-runner/actions-runner/run.sh --jitconfig "$jit"

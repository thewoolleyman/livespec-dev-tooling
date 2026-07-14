#!/usr/bin/env bash
# run-jit-runner.sh — ExecStart for runner@.service. Reads the one-shot JIT config
# that systemd staged via LoadCredential (ci-runner-only $CREDENTIALS_DIRECTORY)
# and execs the runner for a single ephemeral job. The JIT config never lands in a
# path the job container can reach (the sanitize-hook mounts only _work).
set -euo pipefail
jit="$(cat "${CREDENTIALS_DIRECTORY}/jit")"
# Run from THIS instance's own directory (the unit's WorkingDirectory), never the
# shared install — concurrent runners must not share a runner root. See runner@.service.
exec ./run.sh --jitconfig "$jit"

#!/usr/bin/env bash
# prepare-runner-slot.sh — create and verify one stable JIT-runner root.
#
# This runs as root through runner-slot-preflight@.service, BEFORE the
# credential-bearing supervisor is allowed to call GitHub.  A JIT config is
# single-use, so discovering a missing WorkingDirectory after minting is not a
# recoverable runner-start failure: it burns a GitHub App request and an
# unbounded supervisor retry turns that local defect into a throttle incident.
set -euo pipefail

INSTANCE="${1:-}"
RUNNER_USER="${CI_RUNNER_USER:-ci-runner}"
RUNNER_HOME="${CI_RUNNER_HOME:-/home/${RUNNER_USER}}"
CANONICAL_ROOT="${CI_RUNNER_CANONICAL_ROOT:-${RUNNER_HOME}/actions-runner}"
INSTANCES_ROOT="${CI_RUNNER_INSTANCES_ROOT:-${RUNNER_HOME}/runners}"
SLOT_ROOT="${INSTANCES_ROOT}/${INSTANCE}"

fail() {
  printf 'runner-slot-preflight: %s\n' "$*" >&2
  exit 1
}

as_runner() {
  if [ "$(id -un)" = "$RUNNER_USER" ]; then
    "$@"
  else
    runuser -u "$RUNNER_USER" -- "$@"
  fi
}

owned_directory() {
  if [ "$(id -u)" -eq 0 ]; then
    install -d -o "$RUNNER_USER" -g "$RUNNER_USER" -m 0755 "$1"
  else
    mkdir -p "$1"
  fi
}

validate_instance() {
  [[ "$INSTANCE" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] \
    || fail "refusing unsafe instance name: ${INSTANCE@Q}"
}

verify_canonical_root() {
  local directory filename
  [ -d "$CANONICAL_ROOT" ] || fail "canonical runner root is absent: $CANONICAL_ROOT"
  for directory in bin externals container-hooks; do
    [ -d "$CANONICAL_ROOT/$directory" ] \
      || fail "canonical runner directory is absent: $CANONICAL_ROOT/$directory"
  done
  [ -x "$CANONICAL_ROOT/bin/Runner.Listener" ] \
    || fail "canonical Runner.Listener is absent or not executable"
  for filename in run.sh run-helper.sh.template config.sh env.sh .env; do
    [ -f "$CANONICAL_ROOT/$filename" ] \
      || fail "canonical runner file is absent: $CANONICAL_ROOT/$filename"
  done
}

materialize_slot() {
  local directory filename
  owned_directory "$INSTANCES_ROOT"
  if [ -e "$SLOT_ROOT" ]; then
    return
  fi

  as_runner mkdir -p "$SLOT_ROOT/_work" "$SLOT_ROOT/_diag"
  for directory in bin externals container-hooks; do
    as_runner cp -al "$CANONICAL_ROOT/$directory" "$SLOT_ROOT/$directory"
  done
  for filename in run.sh run-helper.sh.template config.sh env.sh .env; do
    as_runner cp -f "$CANONICAL_ROOT/$filename" "$SLOT_ROOT/$filename"
  done
  for filename in run-helper.cmd.template safe_sleep.sh; do
    [ -e "$CANONICAL_ROOT/$filename" ] \
      && as_runner cp -f "$CANONICAL_ROOT/$filename" "$SLOT_ROOT/$filename" \
      || true
  done
}

verify_slot() {
  local directory filename
  [ -d "$SLOT_ROOT" ] && [ ! -L "$SLOT_ROOT" ] \
    || fail "slot root is absent or not a real directory: $SLOT_ROOT"
  for directory in bin externals container-hooks; do
    [ -d "$SLOT_ROOT/$directory" ] && [ ! -L "$SLOT_ROOT/$directory" ] \
      || fail "slot directory is absent or symlinked: $SLOT_ROOT/$directory"
  done
  [ -x "$SLOT_ROOT/bin/Runner.Listener" ] \
    || fail "slot Runner.Listener is absent or not executable: $SLOT_ROOT/bin/Runner.Listener"
  [ "$CANONICAL_ROOT/bin/Runner.Listener" -ef "$SLOT_ROOT/bin/Runner.Listener" ] \
    || fail "slot Runner.Listener is not hard-linked to the canonical runner root"
  for filename in run.sh run-helper.sh.template config.sh env.sh .env; do
    [ -f "$SLOT_ROOT/$filename" ] \
      || fail "slot runner file is absent: $SLOT_ROOT/$filename"
  done
  for directory in _work _diag; do
    [ -d "$SLOT_ROOT/$directory" ] && [ ! -L "$SLOT_ROOT/$directory" ] \
      || fail "slot mutable directory is absent or symlinked: $SLOT_ROOT/$directory"
  done
}

validate_instance
verify_canonical_root
materialize_slot
verify_slot
printf 'runner-slot-preflight: ready %s\n' "$INSTANCE"

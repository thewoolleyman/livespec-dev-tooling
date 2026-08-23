#!/usr/bin/env bash
# gate-optin-expiry.sh — enforce the 24-hour wall-clock expiry on the gate
# supervisor's operator opt-in (/run/livespec-local-ci-enabled).
#
# Obligation: livespec SPECIFICATION/non-functional-requirements.md
# §"Fleet CI execution posture" (v214, livespec-s43svm.43): the opt-in "MUST
# carry a wall-clock expiry enforced on the host of no more than 24 hours from
# the opt-in's creation, and an opt-in MUST NOT be extended, renewed, or
# re-created by anything other than a fresh explicit operator act"; "a gate
# supervisor found active with no opt-in present, or with an opt-in past its
# expiry, is a violation".
#
# WHAT THIS SCRIPT DOES: if the opt-in exists and is older than MAX_AGE_SECONDS,
# it REMOVES the opt-in, logs the creation time and age to the journal, and
# stops gate-runner-supervisor.service. Nothing else.
#
# WHAT IT NEVER DOES: create, touch, or otherwise refresh the opt-in. The
# WRITER set for the opt-in is exactly one thing — gate-optin.sh, run by an
# operator — so that no timer can ever re-arm an opt-in the clause says must
# lapse. If you are tempted to add a "refresh" path here, re-read the clause.
#
# WHY THE EXPLICIT `systemctl stop`: hosted-only.conf gates the supervisor with
# ConditionPathExists=/run/livespec-local-ci-enabled, but systemd evaluates
# unit conditions ONLY when a start is attempted (systemd.unit(5), "Conditions
# and Asserts": conditions are checked before the unit is started; a unit that
# is already running is NOT stopped when its condition later becomes false).
# Removing the file alone would therefore leave the supervisor resident until
# its next restart — on a long-uptime host, indefinitely. Stopping it here is
# what makes the expiry real.
#
# MID-RUN SAFETY: stopping the supervisor does NOT interrupt a gate job in
# flight. The supervisor starts gate-runner@<name>.service as a SEPARATE unit
# (no Requires=/BindsTo= either way) and merely waits for it; the JIT runner
# loaded its credential at start (LoadCredential= copies it) and auto-
# deregisters after its single job regardless of whether the supervisor is
# still watching. The only thing lost is the supervisor's own post-job
# `rm -f` of the staged .jit file, which systemd already removes with the
# supervisor's RuntimeDirectory on stop. So this script stops the supervisor
# IMMEDIATELY rather than deferring while a gate-runner@ instance is active:
# deferral would re-introduce an unbounded window (a long-running gate job)
# and the clause names an active supervisor past expiry a violation with no
# in-flight exception.
#
# CREATION TIME: birth time (`stat -c %W`) is the creation instant the clause
# speaks of. /run is tmpfs, which carries birth time on every kernel this
# fleet runs (verified on the live host). If a filesystem reports no birth time
# (%W prints 0 or -), the script falls back to mtime — which for a file that
# nothing but `touch` creates, and that no sanctioned path re-touches, equals
# the creation time. The fallback is logged so the journal says which was used.
set -euo pipefail

OPTIN=/run/livespec-local-ci-enabled
SUPERVISOR=gate-runner-supervisor.service
# 24h is the ceiling the clause names ("no more than 24 hours"); this is the
# one place it is encoded, and it MUST NOT be raised above 86400.
MAX_AGE_SECONDS="${GATE_OPTIN_MAX_AGE_SECONDS:-86400}"
[ "$MAX_AGE_SECONDS" -le 86400 ] \
  || { echo "FATAL: GATE_OPTIN_MAX_AGE_SECONDS=${MAX_AGE_SECONDS} exceeds the 24h ceiling the spec names" >&2; exit 2; }

log() { printf 'gate-optin-expiry: %s\n' "$*"; }

if [ ! -e "$OPTIN" ]; then
  # No opt-in. The supervisor MUST NOT be active either; if it is, that is the
  # clause's other violation shape ("active with no opt-in present") — most
  # likely a hand-started unit after a hand-removed file. Stop it and say so.
  if systemctl is-active --quiet "$SUPERVISOR"; then
    log "VIOLATION: ${SUPERVISOR} is active with no opt-in at ${OPTIN} — stopping it"
    systemctl stop "$SUPERVISOR"
  else
    log "no opt-in present; ${SUPERVISOR} inactive — nothing to do"
  fi
  exit 0
fi

now="$(date +%s)"
created="$(stat -c %W "$OPTIN")"
source=birth
if [ -z "$created" ] || [ "$created" = "-" ] || [ "$created" -le 0 ]; then
  created="$(stat -c %Y "$OPTIN")"
  source="mtime (birth time unsupported on this filesystem)"
fi
age=$(( now - created ))
created_iso="$(date -u -d "@${created}" +%Y-%m-%dT%H:%M:%SZ)"

if [ "$age" -le "$MAX_AGE_SECONDS" ]; then
  log "opt-in created ${created_iso} (${source}), age ${age}s <= ${MAX_AGE_SECONDS}s — still valid; expires at $(date -u -d "@$(( created + MAX_AGE_SECONDS ))" +%Y-%m-%dT%H:%M:%SZ)"
  exit 0
fi

log "opt-in created ${created_iso} (${source}) is ${age}s old, past the ${MAX_AGE_SECONDS}s ceiling — removing ${OPTIN}"
rm -f "$OPTIN"
if systemctl is-active --quiet "$SUPERVISOR"; then
  log "stopping ${SUPERVISOR} (its ConditionPathExists is only re-evaluated on start, so removal alone would leave it resident)"
  systemctl stop "$SUPERVISOR"
fi
log "expired: opt-in removed at $(date -u +%Y-%m-%dT%H:%M:%SZ); a fresh operator act (gate-optin.sh) is the only way to opt in again"

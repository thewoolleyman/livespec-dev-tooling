#!/usr/bin/env bash
# gate-optin.sh — THE sanctioned "fresh explicit operator act" that opts the
# shared factory host into running the privileged gate supervisor for the next
# 24 hours. Run as root (sudo).
#
#   gate-optin.sh          create the opt-in; FAILS if one already exists
#   gate-optin.sh --renew  remove the existing opt-in and create a fresh one
#                          (logged as a renewal — still an explicit operator act)
#   gate-optin.sh --revoke remove the opt-in now and stop the supervisor
#
# Obligation: livespec SPECIFICATION/non-functional-requirements.md §"Fleet CI
# execution posture" (v214, livespec-s43svm.43): the opt-in MUST carry a 24h
# wall-clock expiry and "MUST NOT be extended, renewed, or re-created by
# anything other than a fresh explicit operator act". This script is that act.
# Hand-`touch`ing /run/livespec-local-ci-enabled is therefore NOT a sanctioned
# path: it bypasses the no-silent-renewal check below and leaves no journal
# record of who opted in when. `--renew` exists precisely so that an operator
# who wants more time performs a NEW explicit act (and says so) instead of
# re-touching the file — the file is removed and re-created, so its birth time
# (which gate-optin-expiry.sh measures) restarts, and the renewal is logged.
#
# Expiry itself is enforced by gate-optin-expiry.timer (every 15 min), which
# removes an opt-in older than 24h and stops the supervisor.
set -euo pipefail

OPTIN=/run/livespec-local-ci-enabled
SUPERVISOR=gate-runner-supervisor.service
MAX_AGE_SECONDS=86400

[ "$(id -u)" -eq 0 ] || { echo "FATAL: run as root (sudo $0 $*)" >&2; exit 1; }

mode="${1:-create}"
case "$mode" in
  create|--renew|--revoke) ;;
  *) echo "usage: $0 [--renew|--revoke]" >&2; exit 2 ;;
esac

# `logger` puts the act in the journal next to the expiry service's lines, so
# the opt-in lifecycle (created / renewed / revoked / expired) reads as one
# record. SUDO_USER names the human behind the sudo, when there is one.
who="${SUDO_USER:-$(id -un)}"
say() { printf 'gate-optin: %s\n' "$*"; logger -t gate-optin -- "$* (by ${who})"; }

if [ "$mode" = "--revoke" ]; then
  if [ -e "$OPTIN" ]; then rm -f "$OPTIN"; say "revoked: removed ${OPTIN}"; else say "revoke: no opt-in present"; fi
  systemctl stop "$SUPERVISOR"
  say "stopped ${SUPERVISOR}"
  exit 0
fi

if [ -e "$OPTIN" ]; then
  if [ "$mode" = "--renew" ]; then
    prev="$(date -u -d "@$(stat -c %W "$OPTIN")" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown)"
    rm -f "$OPTIN"
    say "renewing: removed existing opt-in (created ${prev}) so the fresh one starts its own 24h window"
  else
    echo "FATAL: ${OPTIN} already exists (created $(stat -c %w "$OPTIN")). The spec forbids silent renewal;" >&2
    echo "       if you deliberately want a fresh 24h window, run: sudo $0 --renew" >&2
    exit 1
  fi
fi

( umask 0022; : > "$OPTIN" )
created="$(stat -c %W "$OPTIN")"
say "created ${OPTIN} at $(date -u -d "@${created}" +%Y-%m-%dT%H:%M:%SZ); expires $(date -u -d "@$(( created + MAX_AGE_SECONDS ))" +%Y-%m-%dT%H:%M:%SZ) (enforced by gate-optin-expiry.timer)"
systemctl start "$SUPERVISOR"
say "started ${SUPERVISOR}"

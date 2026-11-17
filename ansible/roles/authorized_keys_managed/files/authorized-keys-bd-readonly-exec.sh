#!/bin/sh
# DRAFT, NOT APPLIED, NOT REVIEWED BY THE MAINTAINER (livespec-dev-tooling-tbhqye, route A).
#
# Forced command for a dolt-tunnel key, installed on the VPS by the
# authorized_keys_managed role when an entry sets `bd_readonly_exec: true`.
#
# Two behaviours, nothing else:
#   1. No client command (the tunnel session): block exactly as the current
#      forced command does, `setpriv --pdeathsig KILL sleep infinity`, so the
#      forward keeps TCP_NODELAY (hetzner-xubuntu-info research note 024).
#   2. A client command that is EXACTLY a read-only bd call:
#        bd <show|list|comments> <args...>
#      with every arg matching the allowed shapes below. It runs the VPS-local
#      pinned guard under the credential wrapper, so one call costs one SSH
#      round trip plus the on-VPS call (about 0.84 s) instead of about 90 Dolt
#      round trips. Anything else exits 126 and runs nothing.
#
# Open design questions for the maintainer (the reason this is a draft):
#   - Which checkout directory bd resolves its .beads tenant from on the VPS;
#     the default below is one repository. A multi-repository allowlist needs a
#     `--repo <name>` token mapped to a fixed directory.
#   - Whether the key may also carry reads of other tenants.
#   - Output size: a full `bd list --json` dump is about 3.6 MB.
set -eu

cmd="${SSH_ORIGINAL_COMMAND:-}"

if [ -z "$cmd" ]; then
  exec /usr/bin/setpriv --pdeathsig KILL /usr/bin/sleep infinity
fi

# Split on spaces only, never glob, never expand.
set -f
# shellcheck disable=SC2086
set -- $cmd

[ "$#" -ge 2 ] || { echo "denied: not a bd read" >&2; exit 126; }
[ "$1" = "bd" ] || { echo "denied: only bd" >&2; exit 126; }

verb="$2"
case "$verb" in
  show|list|comments) ;;
  *) echo "denied: verb $verb is not read-only allowlisted" >&2; exit 126 ;;
esac

shift 2
for arg in "$@"; do
  case "$arg" in
    --json|--all|--limit|--status) ;;
    *[!A-Za-z0-9._-]*|"") echo "denied: argument shape" >&2; exit 126 ;;
    -*) echo "denied: flag $arg" >&2; exit 126 ;;
  esac
done

cd "${AUTHORIZED_KEYS_BD_READONLY_DIR:-/data/projects/livespec-dev-tooling}"
exec /usr/local/bin/with-livespec-env.sh -- /usr/local/bin/bd "$verb" "$@"

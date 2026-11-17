#!/bin/sh
# DRAFT, NOT APPLIED. Whether to switch it on at all is still the maintainer's
# decision (livespec-dev-tooling-tbhqye, route A).
#
# Forced command for a dolt-tunnel key, installed on the VPS by the
# authorized_keys_managed role when an entry sets `bd_readonly_exec: true`.
#
# Two behaviours, nothing else:
#   1. No client command (the tunnel session): block exactly as the current
#      forced command does, `setpriv --pdeathsig KILL sleep infinity`, so the
#      forward keeps TCP_NODELAY (hetzner-xubuntu-info research note 024).
#   2. A client command that is EXACTLY
#        in <repo> bd <show|list|comments> <args...>
#      where <repo> is an exact line of the allowlist file written by the
#      role (/etc/authorized-keys-bd-readonly-exec/repos, one repository
#      directory name per line, from `bd_readonly_exec_repos`). The tenant is
#      resolved only as /data/projects/<repo>, never from a client-supplied
#      path. It runs the VPS-local pinned guard under the credential wrapper,
#      so one call costs one SSH round trip plus the on-VPS call (about 0.84 s)
#      instead of about 90 Dolt round trips. Anything else exits 126 and runs
#      nothing.
#
# Maintainer rulings (relayed 2026-11-17): the exec may read every fleet
# tenant, and there is no output size cap (the cost is latency, not bandwidth,
# so one large read is cheaper than many small ones).
set -eu

ALLOWLIST="${AUTHORIZED_KEYS_BD_READONLY_REPOS:-/etc/authorized-keys-bd-readonly-exec/repos}"
PROJECTS="${AUTHORIZED_KEYS_BD_READONLY_PROJECTS:-/data/projects}"

cmd="${SSH_ORIGINAL_COMMAND:-}"

if [ -z "$cmd" ]; then
  exec /usr/bin/setpriv --pdeathsig KILL /usr/bin/sleep infinity
fi

# Split on spaces only, never glob, never expand.
set -f
# shellcheck disable=SC2086
set -- $cmd

[ "$#" -ge 4 ] || { echo "denied: not an in <repo> bd <verb> call" >&2; exit 126; }
[ "$1" = "in" ] || { echo "denied: expected 'in <repo>'" >&2; exit 126; }
repo="$2"
[ "$3" = "bd" ] || { echo "denied: only bd" >&2; exit 126; }
verb="$4"

case "$repo" in
  ""|*[!A-Za-z0-9._-]*) echo "denied: repository name shape" >&2; exit 126 ;;
esac
grep -Fxq -- "$repo" "$ALLOWLIST" 2>/dev/null || { echo "denied: repository $repo is not allowlisted" >&2; exit 126; }
[ -d "$PROJECTS/$repo/.beads" ] || { echo "denied: no tenant for $repo" >&2; exit 126; }

case "$verb" in
  show|list|comments) ;;
  *) echo "denied: verb $verb is not read-only allowlisted" >&2; exit 126 ;;
esac

shift 4
for arg in "$@"; do
  case "$arg" in
    --json|--all|--limit|--status) ;;
    *[!A-Za-z0-9._-]*|"") echo "denied: argument shape" >&2; exit 126 ;;
    -*) echo "denied: flag $arg" >&2; exit 126 ;;
  esac
done

cd "$PROJECTS/$repo"
exec /usr/local/bin/with-livespec-env.sh -- /usr/local/bin/bd "$verb" "$@"

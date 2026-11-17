#!/bin/bash
# Forced command for a dolt-tunnel key (livespec-dev-tooling-tbhqye, route A).
# Installed on the VPS by the authorized_keys_managed role when an entry sets
# `bd_exec: true`. NOT APPLIED until the independent second look and the apply.
#
# Two behaviours, nothing else:
#   1. No client command (the connection's own session, held by the tunnel
#      unit): block exactly as the previous forced command did,
#      `setpriv --pdeathsig KILL sleep infinity`, so the forward keeps
#      TCP_NODELAY (hetzner-xubuntu-info research note 024).
#   2. A client command that is EXACTLY
#        in <repo> bd <base64 of the NUL-separated bd argv>
#      where <repo> is an exact line of the allowlist file the role writes
#      (/etc/authorized-keys-bd-exec/repos). The tenant directory is only
#      /data/projects/<repo>, never a client path. The argv is decoded into an
#      array and exec'd with no shell, so a title or comment with spaces or
#      quotes cannot inject anything. One call is one SSH round trip plus the
#      on-VPS bd call (about 0.84 s) instead of about 90 Dolt round trips.
#      Everything else exits 126 and runs nothing.
#
# Reads AND writes are allowed (the tunnel already forwards full read/write
# SQL, so this adds no capability). Denied: verbs and flags that touch the VPS
# filesystem or the database connection. Every tenant in the allowlist is
# reachable, with no output cap.
set -eu

ALLOWLIST="${AUTHORIZED_KEYS_BD_EXEC_REPOS:-/etc/authorized-keys-bd-exec/repos}"
PROJECTS="${AUTHORIZED_KEYS_BD_EXEC_PROJECTS:-/data/projects}"
RUN_PREFIX="${AUTHORIZED_KEYS_BD_EXEC_RUN:-/usr/local/bin/with-livespec-env.sh -- /usr/local/bin/bd}"

deny() { echo "denied: $1" >&2; exit 126; }

cmd="${SSH_ORIGINAL_COMMAND:-}"

if [ -z "$cmd" ]; then
  exec /usr/bin/setpriv --pdeathsig KILL /usr/bin/sleep infinity
fi

set -f
# shellcheck disable=SC2086
set -- $cmd
[ "$#" -eq 4 ] || deny "not 'in <repo> bd <b64>'"
[ "$1" = "in" ] || deny "expected 'in <repo>'"
repo="$2"
[ "$3" = "bd" ] || deny "only bd"
b64="$4"

case "$repo" in
  ""|*[!A-Za-z0-9._-]*) deny "repository name shape" ;;
esac
grep -Fxq -- "$repo" "$ALLOWLIST" 2>/dev/null || deny "repository $repo is not allowlisted"
[ -d "$PROJECTS/$repo/.beads" ] || deny "no tenant for $repo"

case "$b64" in
  ""|*[!A-Za-z0-9+/=]*) deny "argument encoding" ;;
esac
args=()
while IFS= read -r -d '' a; do args+=("$a"); done < <(printf '%s' "$b64" | base64 -d 2>/dev/null; printf '\0')
[ "${#args[@]}" -ge 1 ] || deny "no bd verb"

verb="${args[0]}"
case "$verb" in
  ""|-*|*[!A-Za-z0-9_-]*) deny "verb shape" ;;
  init|sql|dolt|import|export|backup|restore|migrate|bootstrap|daemon|mcp|setup|hooks|serve|server) deny "verb $verb touches the host" ;;
esac

for a in "${args[@]}"; do
  case "$a" in
    --db|--db=*|--database|--database=*|--dolt-*|--host|--host=*|--port|--port=*|--file|--file=*|--body-file|--body-file=*|--design-file|--design-file=*|-f|--path|--path=*|--dir|--dir=*|--config|--config=*|--output|--output=*|-o|--jsonl|--jsonl=*)
      deny "flag $a names a host path or connection" ;;
  esac
done

cd "$PROJECTS/$repo"
# shellcheck disable=SC2086
exec $RUN_PREFIX "${args[@]}"

#!/bin/bash
# Forced command for a dolt-tunnel key (livespec-dev-tooling-tbhqye, route A).
# Installed on the VPS by the authorized_keys_managed role when an entry sets
# `bd_exec: true`.
#
# Two behaviours, nothing else:
#   1. No client command (the connection's own session, held by the tunnel
#      unit): block exactly as the previous forced command did,
#      `setpriv --pdeathsig KILL sleep infinity`, so the forward keeps
#      TCP_NODELAY (hetzner-xubuntu-info research note 024).
#   2. A client command that is EXACTLY
#        in <repo> bd <base64 of the NUL-separated bd argv>
#      where <repo> is an exact line of the allowlist file the role writes.
#      The tenant directory is only /data/projects/<repo>, never a client
#      path. The argv is decoded into an array and exec'd with no shell.
#      Everything else exits 126 and runs nothing.
#
# The paths below are CONSTANTS. They are deliberately not overridable from
# the environment: sshd SetEnv/AcceptEnv must never be able to redirect the
# allowlist or the command. Tests rewrite these three lines in a temporary
# copy of this file (see tests/test_authorized_keys_bd_exec_wrapper.py).
ALLOWLIST=/etc/authorized-keys-bd-exec/repos
PROJECTS=/data/projects
RUN_PREFIX="/usr/local/bin/with-livespec-env.sh -- /usr/local/bin/bd"
set -eu

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

# VERB ALLOWLIST (issue reads and writes only), kept identical to the client's
# list in livespec-orchestrator-beads-fabro bd-guard/bd-remote.sh: a verb not
# here is denied on the server and runs LOCALLY on the client.
verb="${args[0]}"
case "$verb" in
  show|list|comments|comment|update|create|close|reopen|delete|dep|search|label|tag|children|count|history|ready|duplicate|duplicates|note|assign|priority|link|query|stale|status|statuses|types|graph|epic|supersede|todo|q|state|set-state|lint|promote|find-duplicates|version) ;;
  config)
    # Only `config get` and `config list`: `config set/unset` would rewrite the
    # VPS checkout's own .beads configuration.
    case "${args[1]:-}" in get|list) ;; *) deny "config only get or list" ;; esac
    ;;
  *) deny "verb is not allowlisted" ;;
esac

# FLAG DENYLIST, case-insensitive: anything that names a host path, a directory,
# the database connection, a credentials file, or the shared database.
for a in "${args[@]}"; do
  l=$(printf '%s' "$a" | tr 'A-Z' 'a-z')
  case "$l" in
    --db|--db=*|--database|--database=*|--dolt-*|--host|--host=*|--port|--port=*|--global|--profile|--profile=*|--directory|--directory=*|-c|-c=*|--file|--file=*|--body-file|--body-file=*|--design-file|--design-file=*|--description-file|--description-file=*|-f|--path|--path=*|--dir|--dir=*|--config|--config=*|--output|--output=*|-o|--jsonl|--jsonl=*|--credentials-file|--credentials-file=*)
      deny "flag names a host path, directory or connection" ;;
  esac
done

cd "$PROJECTS/$repo"
# shellcheck disable=SC2086
exec $RUN_PREFIX "${args[@]}"

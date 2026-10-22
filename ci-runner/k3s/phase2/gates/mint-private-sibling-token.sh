#!/usr/bin/env bash
# Mint one read-only installation token for precisely the private siblings a
# delegated gate names.  This runs on the pushing host under with-livespec-env;
# stdout is captured by the gate client and never forwarded to a manifest or log.
set -euo pipefail

repo_root=""
while [ $# -gt 0 ]; do
  case "$1" in
    --repo-root) repo_root="$2"; shift 2 ;;
    *) echo "FATAL: unknown argument $1" >&2; exit 2 ;;
  esac
done
[ -d "${repo_root}" ] || { echo "FATAL: --repo-root is required" >&2; exit 2; }

config="${repo_root}/.livespec.jsonc"
[ -f "${config}" ] || { printf '%s\n' '{"private_siblings":[]}'; exit 0; }

mapfile -t rows < <(awk '
  /"cross_repo_targets"[ 	]*:/ { inside=1; next }
  inside && match($0, /"[^"]+"[ 	]*:[ 	]*\{/) { name=substr($0,RSTART+1,RLENGTH); sub(/"[ 	]*:.*$/, "", name) }
  inside && name && match($0, /"github_url"[ 	]*:[ 	]*"[^"]+"/) { url=substr($0,RSTART,RLENGTH); sub(/^.*"github_url"[ 	]*:[ 	]*"/, "", url); sub(/"$/, "", url); print name "\t" url; name="" }
' "${config}")

private=()
for row in "${rows[@]}"; do
  name="${row%%$'\t'*}"; url="${row#*$'\t'}"
  git ls-remote --exit-code "${url}" HEAD >/dev/null 2>&1 || private+=("${name}")
done
[ "${#private[@]}" -gt 0 ] || { printf '%s\n' '{"private_siblings":[]}'; exit 0; }

: "${GITHUB_APP_ID:?missing GITHUB_APP_ID}"; : "${GITHUB_PRIVATE_KEY:?missing GITHUB_PRIVATE_KEY}"
key="$(mktemp)"; trap 'rm -f "${key}"' EXIT; chmod 600 "${key}"
printf '%s' "${GITHUB_PRIVATE_KEY}" | sed -E 's/(-----BEGIN [^-]+-----)/\1\n/; s/(-----END [^-]+-----)/\n\1\n/' > "${key}"
b64url() { openssl base64 -A | tr '+/' '-_' | tr -d '='; }
now="$(date +%s)"; unsigned="$(printf '%s' '{"alg":"RS256","typ":"JWT"}' | b64url).$(printf '{"iat":%s,"exp":%s,"iss":"%s"}' "$((now-60))" "$((now+540))" "${GITHUB_APP_ID}" | b64url)"
jwt="${unsigned}.$(printf '%s' "${unsigned}" | openssl dgst -sha256 -sign "${key}" -binary | b64url)"
first_url="${rows[0]#*$'\t'}"; repository="${first_url#https://github.com/}"
installation="$(curl -fsS -H "Authorization: Bearer ${jwt}" -H 'Accept: application/vnd.github+json' "https://api.github.com/repos/${repository}/installation" | jq -r '.id // empty')"
[ -n "${installation}" ] || { echo 'FATAL: cannot discover the GitHub App installation for private siblings' >&2; exit 1; }
payload="$(printf '%s\n' "${private[@]}" | jq -R . | jq -s '{repositories: ., permissions: {contents: "read"}}')"
response="$(curl -fsS -X POST -H "Authorization: Bearer ${jwt}" -H 'Accept: application/vnd.github+json' "https://api.github.com/app/installations/${installation}/access_tokens" -d "${payload}")"
token="$(printf '%s' "${response}" | jq -r '.token // empty')"
[ -n "${token}" ] || { echo 'FATAL: GitHub did not mint the private sibling installation token' >&2; exit 1; }
jq -nc --arg token "${token}" --args "${private[@]}" '{private_siblings: $ARGS.positional, token: $token}'

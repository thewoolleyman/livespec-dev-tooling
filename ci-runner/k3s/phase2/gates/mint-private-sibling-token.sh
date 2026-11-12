#!/usr/bin/env bash
# mint-private-sibling-token.sh — name the PRIVATE cross-repo siblings of one
# repository and mint the single read-only installation token a delegated gate
# Job needs to clone exactly those — the delegated pre-push gate's
# cross-repository siblings rule in SPECIFICATION/contracts.md, work-item
# livespec-dev-tooling-7kvh2d.
#
# WHERE THIS RUNS, AND WHY NOT IN THE POD. It runs on the PUSHING HOST, invoked
# by `livespec_dev_tooling.gate_remote_delegate` THROUGH
# `/usr/local/bin/with-livespec-env.sh`, which is the only thing that can see
# the fleet GitHub App's credentials: they are projected from 1Password by that
# wrapper, which SCRUBS the caller's environment, so this script cannot be
# handed them and the gate pod can never hold them. The pod receives a token
# scoped to the siblings of ONE run and nothing else.
#
# WHAT IT WRITES. Exactly one JSON object on stdout:
#
#   {"private_siblings": ["<name>", ...], "token": "<installation token>"}
#
# and `{"private_siblings":[]}` when nothing private was found. The client
# captures stdout and passes only the NAMES to the renderer; the token reaches
# the one Job through a per-run Secret it owns. Nothing here prints the token to
# stderr, and no failure message quotes a response body, because the contract
# forbids the token reaching a manifest, a log or a termination message.
#
# EVERY FAILURE IS FAIL-CLOSED. A non-zero exit is reported by the client as a
# step that did not complete, which is a MISSING VERDICT and refuses the push.
# That is the required direction: the alternative — carrying on without a token
# — hands the gate's recipe an EMPTY tree where a cited sibling should be, and
# an absent citation target reads as green.
set -euo pipefail

repo_root=""
while [ $# -gt 0 ]; do
  case "$1" in
    --repo-root) repo_root="$2"; shift 2 ;;
    *) echo "FATAL: unknown argument $1" >&2; exit 2 ;;
  esac
done
[ -n "${repo_root}" ] && [ -d "${repo_root}" ] || {
  echo "FATAL: --repo-root must name an existing directory" >&2; exit 2; }

config="${repo_root}/.livespec.jsonc"
[ -f "${config}" ] || { printf '%s\n' '{"private_siblings":[]}'; exit 0; }

# The same `cross_repo_targets` block the renderer reads, read the same way it
# reads it — by scanning for the `"<name>": {` / `"github_url": "<url>"` pair
# rather than with a JSON parser, because `.livespec.jsonc` carries comments and
# no jsonc parser is available on every host this must run on.
mapfile -t rows < <(awk '
  /"cross_repo_targets"[ \t]*:/ { inside = 1; next }
  inside && match($0, /"[^"]+"[ \t]*:[ \t]*\{/) {
    name = substr($0, RSTART + 1, RLENGTH); sub(/"[ \t]*:.*$/, "", name)
  }
  inside && name && match($0, /"github_url"[ \t]*:[ \t]*"[^"]+"/) {
    url = substr($0, RSTART, RLENGTH)
    sub(/^.*"github_url"[ \t]*:[ \t]*"/, "", url); sub(/"$/, "", url)
    print name "\t" url; name = ""
  }
' "${config}")

# --- CLASSIFY: an ANONYMOUS probe of each sibling's url -----------------------
# THE MECHANISM IS NAMED HERE because the token's scope rests on it: a public
# sibling answers an unauthenticated `ls-remote` and a private one does not, so
# the probe asks precisely the question the gate pod will ask when it clones
# anonymously. The credential helpers are CLEARED and the terminal prompt
# disabled, because a pushing host that holds a git credential for a private
# sibling would otherwise answer the probe with ITS OWN authority and the
# sibling would be classified public — after which the pod's anonymous clone
# fails and the gate is red for the wrong reason.
#
# A probe that fails because the NETWORK is down classifies a public sibling as
# private. That is the safe direction and it stays safe: the mint below then
# names a repository the App may not cover, GitHub refuses it, and the push is
# refused as a missing verdict rather than gated against an absent clone.
private_names=()
private_urls=()
for row in ${rows[@]+"${rows[@]}"}; do
  name="${row%%$'\t'*}"
  url="${row#*$'\t'}"
  if GIT_TERMINAL_PROMPT=0 git -c credential.helper= -c core.askPass=/bin/true \
      ls-remote --exit-code "${url}" HEAD > /dev/null 2>&1; then
    continue
  fi
  private_names+=("${name}")
  private_urls+=("${url}")
done
[ "${#private_names[@]}" -gt 0 ] || { printf '%s\n' '{"private_siblings":[]}'; exit 0; }

# --- MINT: one installation token, scoped to exactly those siblings ----------
: "${GITHUB_APP_ID:?FATAL: GITHUB_APP_ID is not projected; run under with-livespec-env.sh}"
: "${GITHUB_PRIVATE_KEY:?FATAL: GITHUB_PRIVATE_KEY is not projected; run under with-livespec-env.sh}"

# The projected key is a SINGLE-LINE PEM (see .ai/fleet-and-secrets.md), and
# `openssl` will not sign with one: the BEGIN/END guards have to sit on their
# own lines before it parses. Written to a 0600 temp file because `openssl
# dgst -sign` takes a path, and removed on every exit path.
key_file="$(mktemp)"
trap 'rm -f "${key_file}"' EXIT
chmod 600 "${key_file}"
printf '%s' "${GITHUB_PRIVATE_KEY}" \
  | sed -E 's/(-----BEGIN [^-]+-----)/\1\n/; s/(-----END [^-]+-----)/\n\1\n/' > "${key_file}"

base64url() { openssl base64 -A | tr '+/' '-_' | tr -d '='; }

# A ten-minute JWT is the maximum GitHub accepts, and `iat` is backdated a
# minute so a pushing host whose clock runs slightly fast is not refused.
now="$(date +%s)"
header="$(printf '%s' '{"alg":"RS256","typ":"JWT"}' | base64url)"
claims="$(printf '{"iat":%s,"exp":%s,"iss":"%s"}' "$((now - 60))" "$((now + 540))" \
  "${GITHUB_APP_ID}" | base64url)"
signature="$(printf '%s' "${header}.${claims}" \
  | openssl dgst -sha256 -sign "${key_file}" -binary | base64url)"
jwt="${header}.${claims}.${signature}"

# GitHub rejects a scope containing a repository this installation does not
# cover with an otherwise unhelpful 422. Ask about EVERY private sibling first,
# so the pushing host can name the repository an operator must add to the App
# installation (or remove from the consumer's set). `-s` deliberately suppresses
# curl's own HTTP-status diagnostic: the repository-specific refusal below is
# the complete no-verdict detail the delegated gate carries to the operator.
installation_response="$(mktemp)"
token_response="$(mktemp)"
trap 'rm -f "${key_file}" "${installation_response}" "${token_response}"' EXIT

# ONE bounded retry for this host's GitHub API calls, the same shape as the gate
# Job's forge_retry (forge-retry.sh). On 2026-11-12 at 16:34Z a pre-push gate was
# refused as a missing verdict on `access_tokens ... error: 500`, and passed on a
# re-run. Retried: a transport failure (status 000), 429, or any 5xx. Every other
# status goes back to the caller as-is, so a 404 "not covered" or a 422 refuses at
# once. MINT_RETRY_ATTEMPTS attempts (default 5), waiting MINT_RETRY_BASE_WAIT
# seconds (default 5) and doubling: 75 s of waiting, inside the JWT's 9 minutes.
# Each attempt logs its status. The response body goes to <out-file> only and is
# never logged, because a token response carries the token.
github_api() {
  local out_file="$1"
  shift
  local attempts="${MINT_RETRY_ATTEMPTS:-5}"
  local wait_s="${MINT_RETRY_BASE_WAIT:-5}"
  local attempt=1 status
  while :; do
    status="$(curl -s -o "${out_file}" -w '%{http_code}' "$@")" || status="000"
    echo ":: gate: mint call attempt ${attempt}/${attempts}: HTTP ${status}" >&2
    case "${status}" in
      000|429|5[0-9][0-9]) ;;
      *) printf '%s\n' "${status}"; return 0 ;;
    esac
    if [ "${attempt}" -ge "${attempts}" ]; then
      printf '%s\n' "${status}"
      return 0
    fi
    sleep "${wait_s}"
    wait_s=$((wait_s * 2))
    attempt=$((attempt + 1))
  done
}

transient_status() {
  case "$1" in 000|429|5[0-9][0-9]) return 0 ;; *) return 1 ;; esac
}

installation_for_repository() {
  local named_repository="$1"
  local status
  local named_installation

  status="$(github_api "${installation_response}" \
    -H "Authorization: Bearer ${jwt}" -H 'Accept: application/vnd.github+json' \
    "https://api.github.com/repos/${named_repository}/installation")"
  if transient_status "${status}"; then
    echo "FATAL: could not determine whether the gate App's installation covers" \
         "${named_repository}: GitHub answered HTTP ${status} on every attempt" >&2
    return 1
  fi
  if [ "${status}" != 200 ]; then
    echo "FATAL: ${named_repository} is not covered: the gate App's installation" \
         "does not cover it" >&2
    return 1
  fi
  named_installation="$(jq -r '.id // empty' < "${installation_response}")"
  if [ -z "${named_installation}" ]; then
    echo "FATAL: ${named_repository} is not covered: the gate App's installation" \
         "does not cover it" >&2
    return 1
  fi
  printf '%s\n' "${named_installation}"
}

installation=""
for private_url in "${private_urls[@]}"; do
  repository="${private_url#https://github.com/}"
  named_installation="$(installation_for_repository "${repository}")" || exit 1
  if [ -z "${installation}" ]; then
    installation="${named_installation}"
  elif [ "${named_installation}" != "${installation}" ]; then
    echo "FATAL: ${repository} is not covered: the gate App's installation" \
         "does not cover it" >&2
    exit 1
  fi
done

# `repositories` is the scope, and it is the private set EXACTLY — never the
# whole installation and never a public sibling that needs no credential.
# `permissions` is `contents: read` alone; GitHub expires the result in an hour,
# which is the ceiling the contract states.
scope="$(printf '%s\n' "${private_names[@]}" | jq -R . \
  | jq -s '{repositories: ., permissions: {contents: "read"}}')"
status="$(github_api "${token_response}" -X POST \
  -H "Authorization: Bearer ${jwt}" -H 'Accept: application/vnd.github+json' \
  "https://api.github.com/app/installations/${installation}/access_tokens" \
  -d "${scope}")"
if [ "${status}" != 201 ]; then
  echo "FATAL: GitHub refused to mint an installation token for this gate's private" \
       "siblings: HTTP ${status}" >&2
  exit 1
fi
token="$(jq -r '.token // empty' < "${token_response}")"
[ -n "${token}" ] || {
  echo "FATAL: GitHub minted no installation token for this gate's private siblings" >&2
  exit 1; }

# `jq -n` rather than string interpolation, so a token containing a JSON
# metacharacter cannot break the one object the client parses.
jq -nc --arg token "${token}" --args '{private_siblings: $ARGS.positional, token: $token}' \
  "${private_names[@]}"

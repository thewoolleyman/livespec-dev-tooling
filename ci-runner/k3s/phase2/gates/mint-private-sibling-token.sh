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

# The installation is discovered from a PRIVATE sibling, never from the first
# declared one: the mint below is made against the installation that can reach
# the repositories it names, and a public sibling may sit outside it entirely.
repository="${private_urls[0]#https://github.com/}"
installation="$(curl -fsS \
  -H "Authorization: Bearer ${jwt}" -H 'Accept: application/vnd.github+json' \
  "https://api.github.com/repos/${repository}/installation" | jq -r '.id // empty')"
[ -n "${installation}" ] || {
  echo "FATAL: the fleet GitHub App has no installation reaching ${repository}," \
       "so no token can be scoped to this gate's private siblings" >&2
  exit 1; }

# `repositories` is the scope, and it is the private set EXACTLY — never the
# whole installation and never a public sibling that needs no credential.
# `permissions` is `contents: read` alone; GitHub expires the result in an hour,
# which is the ceiling the contract states.
scope="$(printf '%s\n' "${private_names[@]}" | jq -R . \
  | jq -s '{repositories: ., permissions: {contents: "read"}}')"
token="$(curl -fsS -X POST \
  -H "Authorization: Bearer ${jwt}" -H 'Accept: application/vnd.github+json' \
  "https://api.github.com/app/installations/${installation}/access_tokens" \
  -d "${scope}" | jq -r '.token // empty')"
[ -n "${token}" ] || {
  echo "FATAL: GitHub minted no installation token for this gate's private siblings" >&2
  exit 1; }

# `jq -n` rather than string interpolation, so a token containing a JSON
# metacharacter cannot break the one object the client parses.
jq -nc --arg token "${token}" --args '{private_siblings: $ARGS.positional, token: $token}' \
  "${private_names[@]}"

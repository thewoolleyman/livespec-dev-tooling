#!/usr/bin/env bash
# app-installation-token.sh — print a short-lived GitHub App installation access
# token (~1h) to stdout. The gate supervisor's POLL credential.
#
# Runs as the SUPERVISOR user (ci-sup), the only account that can read the App
# private key. The key never leaves this process; nothing is echoed but the token.
#
# Deliberately separate from mint-jitconfig.sh: that script is the proven minting
# path for the contained CI lane and is left untouched. Both derive an installation
# token from the same App JWT, so the ~10 lines of RS256 signing are repeated here
# rather than refactoring a live, load-bearing credential path.
#
# Requires: APP_ID, INSTALLATION_ID, and APP_KEY (pem path) or APP_KEY_PEM (content).
set -euo pipefail

: "${APP_ID:?}"; : "${INSTALLATION_ID:?}"

_tmpkey=""
cleanup() { [ -n "$_tmpkey" ] && rm -f "$_tmpkey"; return 0; }  # never poison exit code
trap cleanup EXIT
if [ -z "${APP_KEY:-}" ] && [ -n "${APP_KEY_PEM:-}" ]; then
  _tmpkey="$(mktemp)"; chmod 600 "$_tmpkey"
  printf '%s' "$APP_KEY_PEM" > "$_tmpkey"
  APP_KEY="$_tmpkey"
fi
: "${APP_KEY:?APP_KEY (file) or APP_KEY_PEM (content) required}"
[ -r "$APP_KEY" ] || { echo "token: cannot read App key $APP_KEY" >&2; exit 1; }

b64url() { openssl base64 -A | tr '+/' '-_' | tr -d '='; }

# --- App JWT (RS256, 9-minute window, 60s clock-skew allowance) ---
now=$(date +%s); iat=$((now - 60)); exp=$((now + 540))
header='{"alg":"RS256","typ":"JWT"}'
payload="{\"iat\":${iat},\"exp\":${exp},\"iss\":\"${APP_ID}\"}"
unsigned="$(printf '%s' "$header" | b64url).$(printf '%s' "$payload" | b64url)"
sig="$(printf '%s' "$unsigned" | openssl dgst -sha256 -sign "$APP_KEY" -binary | b64url)"
jwt="${unsigned}.${sig}"

resp="$(curl -sS -X POST \
  -H "Authorization: Bearer ${jwt}" -H "Accept: application/vnd.github+json" \
  "https://api.github.com/app/installations/${INSTALLATION_ID}/access_tokens")"
tok="$(printf '%s' "$resp" | jq -r '.token // empty')"
[ -n "$tok" ] || { echo "token: no installation token: $(printf '%s' "$resp" | jq -r '.message // "unknown"')" >&2; exit 1; }

printf '%s' "$tok"

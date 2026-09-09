#!/usr/bin/env bash
# gha-runner-github-token.sh -- print ONE short-lived GitHub token to stdout.
#
#   gha-runner-github-token.sh --installation [<hosts/NAME.env>]
#   gha-runner-github-token.sh --registration [<hosts/NAME.env>]
#
# --installation prints a GitHub App installation access token (~1h).
# --registration prints a self-hosted-runner REGISTRATION token (~1h) for the
# repository the host values name.
#
# WHY MINT RATHER THAN CARRY. A registration token expires in about an hour, so
# a stored one is a dead value by the time anyone re-runs the installer. Minting
# it from the App credential adds NO new secret: the App id and private key are
# already projected by the registration wrapper the host values name.
#
# WHICH APP. Deliberately NOT the livespec Environment's GITHUB_APP_ID. That is
# thewoolleyman-factory-bot (App 3668528), whose installation permission set has
# `administration` ABSENT (livespec-orchestrator-beads-fabro
# plan/archive/fabro-on-hp/research/006-credential-cutover-runbook.md), and
# `administration: write` is exactly what the registration-token endpoint
# requires. The host values instead name the github-ci-runners Environment's
# App -- the one ARC registers this repository's ephemeral runners through
# today -- which both HAS the permission and is the least-privilege source
# livespec-dev-tooling ci-runner/k3s/README.md "Credential separation" reserves
# for minting runner registrations. See ./README.md "Two credentials, two Apps".
#
# THE CREDENTIAL IS READ FROM THE ENVIRONMENT, never from a file and never from
# argv. Run this UNDER the registration wrapper the host values name:
#
#   with-github-ci-runners-env.sh -- gha-runner-github-token.sh --registration
#
# Nothing but the token is ever printed on stdout; the PEM never leaves this
# process except through a mode-0600 temp file that is removed on exit.
#
# Deps: curl, jq, openssl -- all present on the system secure_path the wrapper
# hard-codes, which is the PATH this runs under.
set -euo pipefail

USAGE="usage: gha-runner-github-token.sh --installation|--registration [<hosts/NAME.env>]"
MODE="${1:?${USAGE}}"
HOST_ENV="${2:-/usr/local/libexec/gha-runner.env}"

case "${MODE}" in
    --installation|--registration) ;;
    *) echo "ERROR: unknown mode '${MODE}'; ${USAGE}" >&2; exit 2 ;;
esac

[[ -r "${HOST_ENV}" ]] || { echo "ERROR: cannot read host values: ${HOST_ENV}" >&2; exit 2; }
# shellcheck source=/dev/null
source "${HOST_ENV}"
: "${GHA_RUNNER_REPO:?${HOST_ENV} must set GHA_RUNNER_REPO}"
: "${GHA_RUNNER_REG_APP_ID_VAR:?${HOST_ENV} must set GHA_RUNNER_REG_APP_ID_VAR}"
: "${GHA_RUNNER_REG_PRIVATE_KEY_VAR:?${HOST_ENV} must set GHA_RUNNER_REG_PRIVATE_KEY_VAR}"
: "${GHA_RUNNER_REG_INSTALLATION_ID_VAR:?${HOST_ENV} must set GHA_RUNNER_REG_INSTALLATION_ID_VAR}"
GITHUB_API="${GITHUB_API_URL:-https://api.github.com}"

# The host values name the VARIABLES; their VALUES come from the wrapper's
# injection. Indirect expansion keeps the App choice in the values file, so
# switching Apps never edits this script.
app_id="${!GHA_RUNNER_REG_APP_ID_VAR:-}"
app_key="${!GHA_RUNNER_REG_PRIVATE_KEY_VAR:-}"
installation_id="${!GHA_RUNNER_REG_INSTALLATION_ID_VAR:-}"

missing=()
[[ -n "${app_id}" ]]  || missing+=("${GHA_RUNNER_REG_APP_ID_VAR}")
[[ -n "${app_key}" ]] || missing+=("${GHA_RUNNER_REG_PRIVATE_KEY_VAR}")
if [[ ${#missing[@]} -gt 0 ]]; then
    # THE FAILURE MODE, MADE LEGIBLE. Name the absent variables and the wrapper
    # that projects them: this script is reached only from the installer and the
    # verifier, and "no App credential" is by far the likeliest reason either
    # fails on a fresh host.
    echo "ERROR: GitHub App credential absent from the environment: ${missing[*]}" >&2
    echo "       These are injected by ${GHA_RUNNER_REG_ENV_WRAPPER:-the registration wrapper}." >&2
    echo "       Run this under it, e.g.:" >&2
    echo "         ${GHA_RUNNER_REG_ENV_WRAPPER:-with-<tenant>-env.sh} -- $0 ${MODE}" >&2
    echo "       Nothing was minted and nothing was changed." >&2
    exit 3
fi

_tmpkey=""
cleanup() { [[ -n "${_tmpkey}" ]] && rm -f "${_tmpkey}"; return 0; }  # never poison the exit code
trap cleanup EXIT

# A secrets manager may deliver the PEM flattened to one line, with the newlines
# stripped or turned into a literal backslash-n. openssl needs real PEM line
# structure, so restore it before writing the key out. Same normalization the
# fleet's Python mint does (livespec-runtime github_auth/signing.py).
normalize_pem() {
    local raw="$1" body begin end compact wrapped
    raw="${raw//\\n/$'\n'}"
    if [[ "${raw}" == *$'\n'* ]]; then printf '%s\n' "${raw}"; return 0; fi
    if [[ "${raw}" =~ ^(-----BEGIN[[:space:]A-Z0-9]*-----)(.*)(-----END[[:space:]A-Z0-9]*-----)$ ]]; then
        begin="${BASH_REMATCH[1]}"; body="${BASH_REMATCH[2]}"; end="${BASH_REMATCH[3]}"
        compact="${body//[[:space:]]/}"
        wrapped="$(printf '%s' "${compact}" | fold -w 64)"
        printf '%s\n%s\n%s\n' "${begin}" "${wrapped}" "${end}"
        return 0
    fi
    printf '%s\n' "${raw}"
}

_tmpkey="$(mktemp)"
chmod 600 "${_tmpkey}"
normalize_pem "${app_key}" > "${_tmpkey}"

b64url() { openssl base64 -A | tr '+/' '-_' | tr -d '='; }

# --- App JWT: RS256, 9-minute window, 60s clock-skew allowance --------------
# Same claim shape the fleet's other two minters use
# (livespec-dev-tooling ci-runner/gate-runner/{app-installation-token,mint-jitconfig}.sh).
now="$(date +%s)"; iat=$((now - 60)); exp=$((now + 540))
header='{"alg":"RS256","typ":"JWT"}'
payload="{\"iat\":${iat},\"exp\":${exp},\"iss\":\"${app_id}\"}"
unsigned="$(printf '%s' "${header}" | b64url).$(printf '%s' "${payload}" | b64url)"
if ! sig="$(printf '%s' "${unsigned}" | openssl dgst -sha256 -sign "${_tmpkey}" -binary | b64url)"; then
    echo "ERROR: openssl could not sign with the App private key; check ${GHA_RUNNER_REG_PRIVATE_KEY_VAR}" >&2
    exit 4
fi
jwt="${unsigned}.${sig}"

api_message() { printf '%s' "$1" | jq -r '.message // "unknown error"'; }

# --- installation id: the pinned one, else discovered for this repository ---
# Discovery keeps the installation-id variable OPTIONAL: an Environment that
# projects only the App id and key still works, at the cost of one extra call.
if [[ -z "${installation_id}" ]]; then
    inst_lookup="$(curl -sS \
        -H "Authorization: Bearer ${jwt}" \
        -H "Accept: application/vnd.github+json" \
        -H "X-GitHub-Api-Version: 2022-11-28" \
        "${GITHUB_API}/repos/${GHA_RUNNER_REPO}/installation")"
    installation_id="$(printf '%s' "${inst_lookup}" | jq -r '.id // empty')"
    [[ -n "${installation_id}" ]] || {
        echo "ERROR: could not resolve the App installation on ${GHA_RUNNER_REPO}: $(api_message "${inst_lookup}")" >&2
        echo "       Either the App is not installed on that repository, or set ${GHA_RUNNER_REG_INSTALLATION_ID_VAR}." >&2
        exit 5; }
fi

# --- installation access token ---------------------------------------------
# curl and jq are kept apart (no pipefail edge) and the FIELD is parsed rather
# than curl's exit status trusted, as the fleet's minters do.
inst_resp="$(curl -sS -X POST \
    -H "Authorization: Bearer ${jwt}" \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "${GITHUB_API}/app/installations/${installation_id}/access_tokens")"
inst_tok="$(printf '%s' "${inst_resp}" | jq -r '.token // empty')"
[[ -n "${inst_tok}" ]] || {
    echo "ERROR: no installation token: $(api_message "${inst_resp}")" >&2; exit 6; }

if [[ "${MODE}" == "--installation" ]]; then
    printf '%s' "${inst_tok}"
    exit 0
fi

# --- runner registration token ---------------------------------------------
# REPOSITORY scope, never organization: `thewoolleyman` is a personal GitHub
# User account, and GitHub's org-level runner endpoints do not exist for
# personal accounts at all -- see livespec-dev-tooling ci-runner/k3s/README.md
# "GitHub registration scope". A 403 here means the App lacks
# `administration: write` on this repository, which is the one thing this
# script cannot work around.
reg_resp="$(curl -sS -X POST \
    -H "Authorization: token ${inst_tok}" \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "${GITHUB_API}/repos/${GHA_RUNNER_REPO}/actions/runners/registration-token")"
reg_tok="$(printf '%s' "${reg_resp}" | jq -r '.token // empty')"
[[ -n "${reg_tok}" ]] || {
    echo "ERROR: no registration token for ${GHA_RUNNER_REPO}: $(api_message "${reg_resp}")" >&2
    echo "       A 403/404 here almost always means the App behind ${GHA_RUNNER_REG_APP_ID_VAR}" >&2
    echo "       lacks 'administration: write' on that repository. Granting it is a" >&2
    echo "       maintainer act on the App installation; no change here can substitute." >&2
    exit 7; }

printf '%s' "${reg_tok}"

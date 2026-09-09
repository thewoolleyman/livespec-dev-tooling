#!/usr/bin/env bash
# gha-runner-register.sh -- register (or re-register) this host's runner with
# the repository the host values name.
#
#   gha-runner-register.sh [--dry-run] [<hosts/NAME.env>]
#
# Runs AS THE RUNNER USER, UNDER the registration wrapper. The gha_runner role invokes it
# that way; the equivalent by hand is:
#
#   sudo -u ubuntu -H /usr/local/bin/with-github-ci-runners-env.sh -- \
#       /usr/local/libexec/gha-runner-register.sh
#
# NOT as root: GitHub's config.sh refuses to run under sudo, and the runner's
# files must be owned by the account the unit runs as.
#
# REGISTER AT INSTALL, NOT AT EVERY START -- the judgement call, recorded.
# Re-registering from an ExecStartPre would put a 1Password resolution and two
# GitHub API calls in front of every restart, so a rate-limited or unreachable
# credential would take down a runner that was otherwise fine, and each restart
# would churn the registration GitHub holds. Registration is therefore an
# INSTALL-time act, and re-registration is cheap because re-running the
# installer is this repo's deploy verb anyway (AGENTS.md: "merging is NOT
# deploying"). Every run passes --replace, so a re-run converges an existing
# registration in place rather than accumulating a second one.
#
# --dry-run resolves and validates everything EXCEPT the two remote calls: it
# proves the credential is present and the runner tree is unpacked, mints
# nothing, and changes nothing.
set -euo pipefail

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then DRY_RUN=1; shift; fi
HOST_ENV="${1:-/usr/local/libexec/gha-runner.env}"
MINTER="${GHA_RUNNER_MINTER:-/usr/local/libexec/gha-runner-github-token.sh}"

[[ -r "${HOST_ENV}" ]] || { echo "ERROR: cannot read host values: ${HOST_ENV}" >&2; exit 2; }
# shellcheck source=/dev/null
source "${HOST_ENV}"

: "${GHA_RUNNER_DIR:?${HOST_ENV} must set GHA_RUNNER_DIR}"
: "${GHA_RUNNER_WORK:?${HOST_ENV} must set GHA_RUNNER_WORK}"
: "${GHA_RUNNER_REPO:?${HOST_ENV} must set GHA_RUNNER_REPO}"
: "${GHA_RUNNER_NAME:?${HOST_ENV} must set GHA_RUNNER_NAME}"
: "${GHA_RUNNER_LABELS:?${HOST_ENV} must set GHA_RUNNER_LABELS}"
: "${GHA_RUNNER_GROUP_NAME:?${HOST_ENV} must set GHA_RUNNER_GROUP_NAME}"
: "${GHA_RUNNER_REG_APP_ID_VAR:?${HOST_ENV} must set GHA_RUNNER_REG_APP_ID_VAR}"
: "${GHA_RUNNER_REG_PRIVATE_KEY_VAR:?${HOST_ENV} must set GHA_RUNNER_REG_PRIVATE_KEY_VAR}"

[[ $(id -u) -ne 0 ]] || {
    echo "ERROR: refusing to run as root -- GitHub's config.sh rejects sudo, and the" >&2
    echo "       runner's files must belong to ${GHA_RUNNER_USER:-the runner user}." >&2
    echo "       the gha_runner role drops to that account for you; by hand use sudo -u." >&2
    exit 2; }

[[ -x "${GHA_RUNNER_DIR}/config.sh" ]] || {
    echo "ERROR: runner release is not unpacked at ${GHA_RUNNER_DIR}/config.sh" >&2; exit 3; }
[[ -x "${MINTER}" ]] || { echo "ERROR: token minter missing: ${MINTER}" >&2; exit 3; }

# Fail on an ABSENT credential here, before anything is minted or written, so
# the message names the wrapper rather than surfacing as a GitHub 401 later.
for var in "${GHA_RUNNER_REG_APP_ID_VAR}" "${GHA_RUNNER_REG_PRIVATE_KEY_VAR}"; do
    [[ -n "${!var:-}" ]] || {
        echo "ERROR: ${var} is absent or empty in this environment." >&2
        echo "       Run under ${GHA_RUNNER_REG_ENV_WRAPPER:-the registration wrapper}:" >&2
        echo "         sudo -u ${GHA_RUNNER_USER:-<user>} -H ${GHA_RUNNER_REG_ENV_WRAPPER:-with-<tenant>-env.sh} -- $0" >&2
        echo "       Nothing was registered and nothing was changed." >&2
        exit 4; }
done

if [[ ${DRY_RUN} -eq 1 ]]; then
    echo "[dry-run] would register ${GHA_RUNNER_NAME} on ${GHA_RUNNER_REPO}"
    echo "[dry-run]   labels     ${GHA_RUNNER_LABELS}"
    echo "[dry-run]   work dir   ${GHA_RUNNER_WORK}"
    echo "[dry-run]   runner dir ${GHA_RUNNER_DIR}"
    echo "[dry-run]   credential ${GHA_RUNNER_REG_APP_ID_VAR} present, ${GHA_RUNNER_REG_PRIVATE_KEY_VAR} present"
    echo "[dry-run] no token minted, no GitHub call made, nothing written"
    exit 0
fi

# The token is a command SUBSTITUTION, never a file and never an exported
# variable: it lives in this shell's memory for the one config.sh call and is
# gone when the process exits. It is passed on config.sh's argv, which is
# visible in /proc for the moments that call runs -- an accepted exposure, since
# the value is a single-use registration token that expires in about an hour and
# the alternative (a file) persists it on disk.
echo "[+] minting a registration token for ${GHA_RUNNER_REPO}"
reg_token="$("${MINTER}" --registration "${HOST_ENV}")"
[[ -n "${reg_token}" ]] || { echo "ERROR: minter returned an empty token" >&2; exit 5; }

echo "[+] configuring ${GHA_RUNNER_NAME} (labels: ${GHA_RUNNER_LABELS})"
(
    cd "${GHA_RUNNER_DIR}"
    # --replace converges an existing registration of the same name instead of
    # failing or creating a second one, which is what makes a re-run idempotent.
    # --disableupdate holds the pin: without it the runner self-upgrades away
    # from the version hosts/<host>.env pins and verifies by checksum.
    ./config.sh \
        --unattended \
        --replace \
        --disableupdate \
        --url "https://github.com/${GHA_RUNNER_REPO}" \
        --token "${reg_token}" \
        --name "${GHA_RUNNER_NAME}" \
        --labels "${GHA_RUNNER_LABELS}" \
        --runnergroup "${GHA_RUNNER_GROUP_NAME}" \
        --work "${GHA_RUNNER_WORK}"
)

# config.sh can exit 0 having written nothing useful; .runner is the artifact
# the launcher refuses to start without, so assert it HERE where the cause is
# still in view.
[[ -f "${GHA_RUNNER_DIR}/.runner" ]] || {
    echo "ERROR: config.sh exited 0 but ${GHA_RUNNER_DIR}/.runner was not written" >&2; exit 6; }
[[ -f "${GHA_RUNNER_DIR}/.credentials" ]] || {
    echo "ERROR: config.sh exited 0 but ${GHA_RUNNER_DIR}/.credentials was not written" >&2; exit 6; }
echo "[ok] registered ${GHA_RUNNER_NAME} on ${GHA_RUNNER_REPO}"

#!/usr/bin/env bash
# install-racadm.sh — install Dell's in-band iDRAC CLI (`racadm`, package
# srvadmin-idracadm7 plus its hardware-access library srvadmin-hapi) on a
# PowerEdge CI runner node, from Dell's OpenManage repository, PINNED by
# version and SHA-256.
#
# WHY IN-BAND racadm: the iDRAC settings this tree owns (apply-idrac-thermal.sh)
# are iDRAC-side, not host-side. The thermal PROFILE has no IPMI raw command;
# it is set through the iDRAC attribute store, which racadm reaches over the
# host's internal IPMI pass-through as root with NO credentials and NO network
# path to the iDRAC. That is what makes the setting reproducible from git on a
# rebuilt node without a secret.
#
# WHY PINNED .deb DOWNLOADS AND NOT `apt-add-repository`: Dell publishes the
# repository per Ubuntu LTS codename (jammy, noble) and the runner host runs a
# newer release than any it lists, so a codename-matched repository line does
# not exist. The two packages are architecture-plain userspace binaries with
# only `openssl` and `pciutils` as dependencies, so the honest install is: fetch
# the two files Dell's Packages index names, verify the SHA-256 the same index
# publishes (recorded below), and let apt install them with their dependencies.
# Bump ALL FOUR pinned values together from the index at
# https://linux.dell.com/repo/community/openmanage/<release>/<codename>/dists/<codename>/main/binary-amd64/Packages
#
# Idempotent: exits 0 without downloading when the pinned version is already
# installed. Requires root and outbound HTTPS to linux.dell.com.
set -euo pipefail

DELL_REPO="https://linux.dell.com/repo/community/openmanage/11000/jammy"
PIN_VERSION="11.0.0.0"
HAPI_FILE="pool/main/s/srvadmin-hapi/srvadmin-hapi_11.0.0.0_amd64.deb"
HAPI_SHA256="13e74ab94519313b175b038d4f9c4cb9aebcb218b25b03664d5b1d8d51a2023d"
RACADM_FILE="pool/main/s/srvadmin-idracadm8/srvadmin-idracadm7_11.0.0.0_all.deb"
RACADM_SHA256="9db342a4f338870330fff3a0d625da6452ad7847a74b87c8534eba84c5fa649b"

log() { printf '\n== %s ==\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "FATAL: must run as root (installs packages)" >&2; exit 1; }
command -v curl >/dev/null || { echo "FATAL: curl not found on PATH" >&2; exit 1; }
command -v sha256sum >/dev/null || { echo "FATAL: sha256sum not found on PATH" >&2; exit 1; }

installed_version() {
  dpkg-query -W -f='${Version}' "$1" 2>/dev/null || true
}

# ---------------------------------------------------------------------------
log "1. Runtime library Dell's package links but does not declare (libargtable2)"
# Ensured BEFORE the pinned-version shortcut below, so a host that got the Dell
# packages without it (the first live install did) is repaired on re-run.
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends libargtable2-0 >/dev/null
echo "libargtable2-0 present"

# ---------------------------------------------------------------------------
log "2. Already at the pinned version?"
if [ "$(installed_version srvadmin-idracadm7)" = "$PIN_VERSION" ] && [ "$(installed_version srvadmin-hapi)" = "$PIN_VERSION" ]; then
  echo "srvadmin-idracadm7 and srvadmin-hapi are already ${PIN_VERSION}; skipping the download."
else
# ---------------------------------------------------------------------------
log "3. Fetch the two pinned packages and verify their SHA-256"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
fetch_and_verify() {
  local rel="$1" sha="$2" out
  out="${WORK}/$(basename "$rel")"
  curl -fsSL --max-time 120 -o "$out" "${DELL_REPO}/${rel}"
  echo "${sha}  ${out}" | sha256sum -c - >/dev/null || { echo "FATAL: SHA-256 mismatch for ${rel}" >&2; exit 1; }
  echo "verified $(basename "$out")"
}
fetch_and_verify "$HAPI_FILE" "$HAPI_SHA256"
fetch_and_verify "$RACADM_FILE" "$RACADM_SHA256"

# ---------------------------------------------------------------------------
log "4. Install (apt resolves the openssl/pciutils dependencies)"
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
  "${WORK}/$(basename "$HAPI_FILE")" "${WORK}/$(basename "$RACADM_FILE")"
fi

# ---------------------------------------------------------------------------
log "5. Verify racadm answers in-band"
RACADM="$(command -v racadm || true)"
[ -n "$RACADM" ] || RACADM="/opt/dell/srvadmin/sbin/racadm"
[ -x "$RACADM" ] || RACADM="/opt/dell/srvadmin/bin/idracadm7"
[ -x "$RACADM" ] || { echo "FATAL: racadm binary not found after install" >&2; exit 1; }
MISSING="$(ldd "$RACADM" 2>/dev/null | awk '/not found/ {print $1}' | tr '\n' ' ')"
[ -z "$MISSING" ] || { echo "FATAL: ${RACADM} is missing shared libraries: ${MISSING}(add their packages to step 3)" >&2; exit 1; }
"$RACADM" getversion >/dev/null || { echo "FATAL: ${RACADM} getversion failed (no in-band iDRAC path?)" >&2; exit 1; }

log "DONE. racadm ${PIN_VERSION} installed at ${RACADM} and answering in-band."

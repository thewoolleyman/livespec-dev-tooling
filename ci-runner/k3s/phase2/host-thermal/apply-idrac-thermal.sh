#!/usr/bin/env bash
# apply-idrac-thermal.sh — converge the PowerEdge CI runner node's iDRAC
# cooling configuration to the fleet-decided state, idempotently, and verify.
#
# THE DECIDED STATE (maintainer-directed, `poweredge-xubuntu-info` FAN_COOLING.md;
# livespec plan `poweredge-raid-array-maintenance`, epic livespec-g52yrb):
#   0. Fan control is AUTOMATIC (the closed thermal loop). Manual/static fan
#      speeds are deliberately never used on a CI box that takes sustained
#      multi-runner bursts; this step re-asserts the loop in case anything left
#      it in manual mode. (2026-09-04: fans sat on the idle floor with CPUs at
#      72 C and 39 runners until re-asserted.)
#   1. The "third-party PCIe card cooling response" is DISABLED. iDRAC8 cannot
#      read temperatures from non-Dell PCIe cards, so with one present it adds a
#      large blanket fan offset (~7.4k RPM at idle vs ~3.9k without). The
#      closed loop on CPU/DIMM/inlet/exhaust/PERC sensors is untouched.
#   2. The thermal profile is "Minimum Power": the least aggressive fan curve.
#      "Maximum Performance" was rejected — a cooling bias for turbo headroom
#      this box never lacks.
#
# WHY racadm FOR STEP 2 AND ipmitool RAW FOR STEPS 0-1: the third-party
# response and the manual/automatic switch are community-documented iDRAC8 OEM
# IPMI commands (0x30 0xce / 0x30 0x30, well-tested on 2.x firmware); the
# thermal profile has no IPMI form and lives in the iDRAC attribute store,
# reachable in-band by racadm (install-racadm.sh) with no credentials.
#
# WHY RE-APPLY AT ALL: all three live in the iDRAC, survive host reboots and OS
# rebuilds, and are lost only on an iDRAC reset-to-defaults or firmware wipe.
# The boot unit that runs this is belt-and-suspenders for exactly that event,
# and running it converges a NEW or REBUILT node with no hand step. Every step
# reads first and writes only on drift, so a converged host makes no changes.
#
# Exit non-zero if any setting cannot be read, or still disagrees after the
# write. Requires root (/dev/ipmi0) and, for step 2, racadm on the host.
set -euo pipefail

THIRD_PARTY_QUERY=(0x30 0xce 0x01 0x16 0x05 0x00 0x00 0x00)
THIRD_PARTY_DISABLE=(0x30 0xce 0x00 0x16 0x05 0x00 0x00 0x00 0x05 0x00 0x01 0x00 0x00)
FAN_AUTO=(0x30 0x30 0x01 0x01)
PROFILE_KEY="System.ThermalSettings.ThermalProfile"
PROFILE_WANT="Minimum Power"

log() { printf '\n== %s ==\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "FATAL: must run as root (/dev/ipmi0)" >&2; exit 1; }
command -v ipmitool >/dev/null || { echo "FATAL: ipmitool not found on PATH" >&2; exit 1; }
[ -c /dev/ipmi0 ] || { echo "FATAL: /dev/ipmi0 absent (ipmi_devintf not loaded?)" >&2; exit 1; }

RACADM="$(command -v racadm || true)"
[ -n "$RACADM" ] || RACADM="/opt/dell/srvadmin/sbin/racadm"
[ -x "$RACADM" ] || RACADM="/opt/dell/srvadmin/bin/idracadm7"
[ -x "$RACADM" ] || { echo "FATAL: racadm not installed — run install-racadm.sh first" >&2; exit 1; }

# ---------------------------------------------------------------------------
log "0. Fan control: re-assert AUTOMATIC (closed thermal loop)"
ipmitool raw "${FAN_AUTO[@]}" >/dev/null
echo "automatic fan control asserted"

# ---------------------------------------------------------------------------
log "1. Third-party PCIe card cooling response: want DISABLED"
# Response is 10 data bytes; the 8th is the state: 0x00 enabled, 0x01 disabled.
third_party_state() {
  ipmitool raw "${THIRD_PARTY_QUERY[@]}" | tr -s ' \n' ' ' | awk '{print $8}'
}
STATE="$(third_party_state)"
case "$STATE" in
  01) echo "already disabled (state byte ${STATE})" ;;
  00) echo "enabled (state byte ${STATE}) — disabling"; ipmitool raw "${THIRD_PARTY_DISABLE[@]}" >/dev/null; sleep 1
      STATE="$(third_party_state)"; [ "$STATE" = "01" ] || { echo "FATAL: state byte is ${STATE} after disable" >&2; exit 1; }
      echo "disabled (state byte ${STATE})" ;;
  *)  echo "FATAL: unrecognised third-party response state byte '${STATE}' — re-verify the raw command against this iDRAC firmware before trusting it" >&2; exit 1 ;;
esac

# ---------------------------------------------------------------------------
log "2. Thermal profile: want \"${PROFILE_WANT}\""
profile_now() {
  "$RACADM" get "$PROFILE_KEY" | sed -n 's/^ThermalProfile=//p' | tr -d '\r' | tail -1
}
NOW="$(profile_now)"
[ -n "$NOW" ] || { echo "FATAL: racadm returned no ThermalProfile value" >&2; exit 1; }
if [ "$NOW" = "$PROFILE_WANT" ]; then
  echo "already \"${NOW}\""
else
  echo "is \"${NOW}\" — setting"
  "$RACADM" set "$PROFILE_KEY" "$PROFILE_WANT" >/dev/null
  NOW="$(profile_now)"
  [ "$NOW" = "$PROFILE_WANT" ] || { echo "FATAL: ThermalProfile is \"${NOW}\" after set" >&2; exit 1; }
  echo "set to \"${NOW}\""
fi

# ---------------------------------------------------------------------------
log "3. Current fan picture (informational)"
ipmitool sdr type fan | grep -E '^Fan[0-9]' | awk -F'|' '{gsub(/ +/," ",$1); gsub(/ +/," ",$5); printf "%s%s;", $1, $5}'
printf '\n'
ipmitool sdr type temperature | awk -F'|' '{gsub(/ +/," ",$1); gsub(/ +/," ",$5); printf "%s%s;", $1, $5}'
printf '\n'

log "DONE. fan control automatic; third-party response disabled; ThermalProfile \"${NOW}\"."

#!/usr/bin/env bash
# install-k3s-config-exit-tests.sh — prove the role-awareness of
# ./install-k3s-config.sh WITHOUT touching any host: that a `server` run does
# what this installer did before it knew about roles, that an `agent` run
# installs ./config.agent.yaml and writes NO packaged-manifest skip marker, and
# that an agent still carrying the SERVER config is REPAIRED — the file replaced
# and the marker removed — with nothing restarted.
#
#   A. ./config.agent.yaml carries no server-only key. This is the fact the
#      whole change rests on and the only one asserted against the committed
#      file rather than against a run: `disable` is not in k3s-agent's flag set,
#      so an agent handed it exits `level=fatal ... flag provided but not
#      defined: -disable` and systemd restart-loops the unit (gmktec-xubuntu
#      2026-09-07, livespec-dev-tooling-vcv4);
#   B. a `server` run on a fresh node installs ./config.yaml byte-for-byte and
#      writes the skip marker — the sequence this installer always ran;
#   C. an `agent` run on a fresh node installs ./config.agent.yaml
#      byte-for-byte, writes NO marker, and does not so much as create the
#      SERVER manifests directory the marker lives in;
#   D. an `agent` run over the state gmktec-xubuntu was left in — the SERVER
#      config at /etc/rancher/k3s/config.yaml and the marker present — replaces
#      the file with the agent copy, names the server-only keys it found,
#      removes the marker, and restarts NOTHING; and a second run is a no-op
#      that says so, since the installer is idempotent;
#   E. the role is validated as data: an unknown role and a stray argument are
#      each refused, naming what was wrong.
#
# HOW IT STAYS OFF THE HOST. Every path the installer writes is resolved under
# `K3S_CONFIG_ROOT`, which each case points at a fresh directory inside this
# suite's own `mktemp -d`. The installer requires root because on a node it
# writes /etc/rancher/k3s, so the executing cases put a fake `id` on PATH ahead
# of the host's — the suite itself never runs as root and never needs to.
# `systemctl` is a TRIPWIRE: this installer must never restart k3s or
# k3s-agent (a restart kills every running CI job on the pool), so case D
# asserts the tripwire records no `restart` at all.
#
# Exit 0 iff every test passes. Mutates nothing outside its own scratch dir.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="${HERE}/install-k3s-config.sh"
SERVER_SRC="${HERE}/config.yaml"
AGENT_SRC="${HERE}/config.agent.yaml"

pass=0; fail=0
ok() { printf '  PASS  %s\n' "$1"; pass=$((pass + 1)); }
no() { printf '  FAIL  %s\n' "$1"; fail=$((fail + 1)); }

TMPROOT="$(mktemp -d)"
case "$TMPROOT" in
  /tmp/*|/var/tmp/*) ;;
  *) echo "FATAL: mktemp -d returned an unexpected path '${TMPROOT}'" >&2; exit 1 ;;
esac
cleanup() { rm -rf "$TMPROOT"; }
trap cleanup EXIT

TRIPWIRE="${TMPROOT}/tripwire"
: > "$TRIPWIRE"
export TRIPWIRE

# The fakes. Each body is single-quoted on purpose: it is the FAKE's source,
# expanded when the fake runs, not when this suite writes it. `systemctl` exits
# 1 so the installer's `is-active` probe reads "not running", which is the state
# a rebuild is done in.
FAKEBIN="${TMPROOT}/fakebin"
mkdir -p "$FAKEBIN"
printf '#!/usr/bin/env bash\necho 0\n' > "${FAKEBIN}/id"
printf '#!/usr/bin/env bash\nprintf "systemctl %%s\\n" "$*" >> "$TRIPWIRE"; exit 1\n' \
  > "${FAKEBIN}/systemctl"
chmod +x "${FAKEBIN}/id" "${FAKEBIN}/systemctl"

# run_install ROOT ARGS... -> stdout+stderr in REPLY_OUT, code in REPLY_RC
run_install() {
  local root="$1"; shift
  REPLY_OUT="$(PATH="${FAKEBIN}:${PATH}" K3S_CONFIG_ROOT="$root" "$SCRIPT" "$@" 2>&1)"
  REPLY_RC=$?
}

new_root() {  # new_root NAME -> a fresh scratch node root on stdout
  local root="${TMPROOT}/$1"
  mkdir -p "${root}/etc" "${root}/var/lib"
  printf '%s' "$root"
}

CONFIG_REL="etc/rancher/k3s/config.yaml"
MARKER_REL="var/lib/rancher/k3s/server/manifests/local-storage.yaml.skip"

# ---------------------------------------------------------------------------
# A. The committed agent config carries no server-only key.
# ---------------------------------------------------------------------------
printf '== A. config.agent.yaml carries only agent-valid keys ==\n'
if [ -f "$AGENT_SRC" ]; then
  ok "config.agent.yaml exists beside the installer"
else
  no "config.agent.yaml exists beside the installer"
fi
# Top-level keys only: a `disable` inside a comment is prose, and the fatal is
# caused by the KEY. Same shallow read the installer itself does.
AGENT_KEYS="$(sed -n 's/^\([A-Za-z][A-Za-z0-9_-]*\):.*$/\1/p' "$AGENT_SRC")"
for forbidden in disable write-kubeconfig-mode; do
  if printf '%s\n' "$AGENT_KEYS" | grep -qx "$forbidden"; then
    no "config.agent.yaml has no '${forbidden}' key"
  else
    ok "config.agent.yaml has no '${forbidden}' key"
  fi
done
if printf '%s\n' "$AGENT_KEYS" | grep -qx 'kubelet-arg'; then
  ok "config.agent.yaml keeps the node-local kubelet-arg the agent needs"
else
  no "config.agent.yaml keeps the node-local kubelet-arg the agent needs"
fi
# The server file is the counter-example that makes the assertion above mean
# something: it DOES carry both keys, which is why it cannot be installed here.
SERVER_KEYS="$(sed -n 's/^\([A-Za-z][A-Za-z0-9_-]*\):.*$/\1/p' "$SERVER_SRC")"
if printf '%s\n' "$SERVER_KEYS" | grep -qx 'disable' \
  && printf '%s\n' "$SERVER_KEYS" | grep -qx 'write-kubeconfig-mode'; then
  ok "config.yaml still carries both server-only keys (the state that is fatal on an agent)"
else
  no "config.yaml still carries both server-only keys (the state that is fatal on an agent)"
fi

# ---------------------------------------------------------------------------
# B. A server run is the sequence this installer always ran.
# ---------------------------------------------------------------------------
printf '\n== B. server, fresh node: config.yaml + the skip marker ==\n'
SROOT="$(new_root server)"
run_install "$SROOT" --role server
if [ "$REPLY_RC" -eq 0 ]; then
  ok "server run exits 0"
else
  no "server run exits 0 (got ${REPLY_RC})"
  printf '%s\n' "$REPLY_OUT"
fi
if cmp -s "$SERVER_SRC" "${SROOT}/${CONFIG_REL}"; then
  ok "server run installs config.yaml byte-for-byte"
else
  no "server run installs config.yaml byte-for-byte"
fi
if [ -e "${SROOT}/${MARKER_REL}" ]; then
  ok "server run writes the local-storage skip marker"
else
  no "server run writes the local-storage skip marker"
fi

# ---------------------------------------------------------------------------
# C. An agent run installs the agent file and writes no marker at all.
# ---------------------------------------------------------------------------
printf '\n== C. agent, fresh node: config.agent.yaml and NO marker ==\n'
AROOT="$(new_root agent)"
run_install "$AROOT" --role agent
if [ "$REPLY_RC" -eq 0 ]; then
  ok "agent run exits 0"
else
  no "agent run exits 0 (got ${REPLY_RC})"
  printf '%s\n' "$REPLY_OUT"
fi
if cmp -s "$AGENT_SRC" "${AROOT}/${CONFIG_REL}"; then
  ok "agent run installs config.agent.yaml byte-for-byte"
else
  no "agent run installs config.agent.yaml byte-for-byte"
fi
if [ -e "${AROOT}/${MARKER_REL}" ]; then
  no "agent run writes no skip marker"
else
  ok "agent run writes no skip marker"
fi
# Not merely "no marker": the SERVER directory it lives in is never created,
# because /var/lib/rancher/k3s/server/ is not an agent's path at all.
if [ -d "${AROOT}/var/lib/rancher/k3s/server" ]; then
  no "agent run does not create the server manifests directory"
else
  ok "agent run does not create the server manifests directory"
fi
if printf '%s\n' "$REPLY_OUT" | grep -q 'config.agent.yaml'; then
  ok "the agent run names the file it installed"
else
  no "the agent run names the file it installed"
fi

# ---------------------------------------------------------------------------
# D. The repair: an agent already carrying the SERVER config and the marker.
#    This IS the state gmktec-xubuntu was left in on 2026-09-07 — the runbook
#    had installed both there, and the first restart of k3s-agent.service after
#    that took the unit into a fatal restart loop.
# ---------------------------------------------------------------------------
printf '\n== D. agent carrying the SERVER config is repaired, nothing restarted ==\n'
RROOT="$(new_root repair)"
mkdir -p "${RROOT}/etc/rancher/k3s" "$(dirname "${RROOT}/${MARKER_REL}")"
cp "$SERVER_SRC" "${RROOT}/${CONFIG_REL}"
: > "${RROOT}/${MARKER_REL}"
: > "$TRIPWIRE"
run_install "$RROOT" --role agent
if [ "$REPLY_RC" -eq 0 ]; then
  ok "the repair run exits 0"
else
  no "the repair run exits 0 (got ${REPLY_RC})"
  printf '%s\n' "$REPLY_OUT"
fi
if cmp -s "$AGENT_SRC" "${RROOT}/${CONFIG_REL}"; then
  ok "the server config on the agent is REPLACED by config.agent.yaml"
else
  no "the server config on the agent is REPLACED by config.agent.yaml"
fi
if [ -e "${RROOT}/${MARKER_REL}" ]; then
  no "the present skip marker is removed"
else
  ok "the present skip marker is removed"
fi
# The operator has to be able to read WHY the file was replaced out of the run's
# own output — the offending keys, not just a diff.
case "$REPLY_OUT" in
  *"REPAIR:"*"SERVER-ONLY key(s):"*disable*write-kubeconfig-mode*)
    ok "the replacement names both server-only keys it found" ;;
  *)
    no "the replacement names both server-only keys it found"
    printf '%s\n' "$REPLY_OUT" ;;
esac
case "$REPLY_OUT" in
  *"live:"*disable*) ok "the replacement prints the live file's keys" ;;
  *) no "the replacement prints the live file's keys" ;;
esac
case "$REPLY_OUT" in
  *"shipped:"*kubelet-arg*) ok "the replacement prints the shipped file's keys" ;;
  *) no "the replacement prints the shipped file's keys" ;;
esac
# The whole point of doing this in the runbook rather than by hand: a restart
# here would kill every running CI job on the pool.
if grep -qi 'restart' "$TRIPWIRE"; then
  no "the repair restarts nothing itself"
  cat "$TRIPWIRE"
else
  ok "the repair restarts nothing itself"
fi

printf '\n== D2. the second agent run is a no-op that says so ==\n'
run_install "$RROOT" --role agent
if [ "$REPLY_RC" -eq 0 ]; then
  ok "the re-run exits 0"
else
  no "the re-run exits 0 (got ${REPLY_RC})"
fi
case "$REPLY_OUT" in
  *"already matches the shipped agent copy"*)
    ok "the re-run reports the config unchanged" ;;
  *)
    no "the re-run reports the config unchanged"
    printf '%s\n' "$REPLY_OUT" ;;
esac
case "$REPLY_OUT" in
  *"no marker present"*) ok "the re-run reports no marker to remove" ;;
  *) no "the re-run reports no marker to remove" ;;
esac
case "$REPLY_OUT" in
  *REPAIR:*) no "the re-run does not claim a repair it did not make" ;;
  *) ok "the re-run does not claim a repair it did not make" ;;
esac

# ---------------------------------------------------------------------------
# E. The role is data, and is validated as data.
# ---------------------------------------------------------------------------
printf '\n== E. role validation ==\n'
VROOT="$(new_root validate)"
run_install "$VROOT" --role worker
if [ "$REPLY_RC" -ne 0 ] && printf '%s\n' "$REPLY_OUT" | grep -q "role must be 'server' or 'agent', got 'worker'"; then
  ok "an unknown role is refused, naming it"
else
  no "an unknown role is refused, naming it (rc=${REPLY_RC}: ${REPLY_OUT})"
fi
if [ -e "${VROOT}/${CONFIG_REL}" ]; then
  no "a refused run installs nothing"
else
  ok "a refused run installs nothing"
fi
run_install "$VROOT" --role
if [ "$REPLY_RC" -ne 0 ] && printf '%s\n' "$REPLY_OUT" | grep -q -- '--role needs a value'; then
  ok "a --role with no value is refused"
else
  no "a --role with no value is refused (rc=${REPLY_RC}: ${REPLY_OUT})"
fi
run_install "$VROOT" server
if [ "$REPLY_RC" -ne 0 ] && printf '%s\n' "$REPLY_OUT" | grep -q "unexpected argument 'server'"; then
  ok "a bare positional argument is refused rather than guessed at"
else
  no "a bare positional argument is refused rather than guessed at (rc=${REPLY_RC}: ${REPLY_OUT})"
fi

# ---------------------------------------------------------------------------
printf '\n%s passed, %s failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]

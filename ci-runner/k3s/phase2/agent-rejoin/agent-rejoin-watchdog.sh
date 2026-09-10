#!/usr/bin/env bash
# agent-rejoin-watchdog.sh — restart a k3s AGENT that is alive-but-wedged after
# the control-plane node's datastore was wiped.
#
# WHY THIS EXISTS. poweredge's k3s datastore is a tmpfs and is EMPTY at every
# boot (R6 of livespec plan k3s-on-gmktec-for-vps-usage), so a poweredge reboot
# drops every agent's Node object from the cluster. gmktec's k3s-agent.service
# does NOT self-heal from that: the process stays UP and simply loops
#   `node "gmktec-xubuntu" not found`
# forever, because `Restart=always` only catches a process that EXITS, not a
# live hang. The manual fix — `systemctl restart k3s-agent` — was proven on
# gmktec-xubuntu on 2026-09-10, but a manual step a reboot silently invalidates
# violates goal 0 (no live host changed by hand). This watchdog is the committed
# mechanism: a timer runs it every ~60s and it restarts the agent ONLY when the
# wedge is unambiguous.
#
# AGENT-ONLY, by construction. poweredge (the self-authoritative server) holds
# the datastore and never loses its OWN registration, so it never wedges; it
# runs k3s.service, not k3s-agent.service, and this watchdog's first gate
# (k3s-agent.service active) is never true there. install-agent-rejoin-watchdog.sh
# refuses to install it on a server for the same reason.
#
# THE FOUR GATES, ALL of which must hold before it acts — so a transient blip,
# an agent that is merely down (Restart=always owns that), an unreachable server
# (nothing to rejoin to), or a just-restarted agent (give it time) never trip it:
#   1. k3s-agent.service is `active` — the process is up, which is the
#      necessary condition for the alive-but-wedged state;
#   2. the control-plane API server named in the agent config is REACHABLE — a
#      restart cannot rejoin a node to a server that is down, so restarting then
#      would be a no-op loop against an outage rather than a repair;
#   3. the agent journal shows `node "<hostname>" not found` at least
#      REJOIN_MIN_HITS times in the last REJOIN_WINDOW_SEC seconds — the
#      signature of the wedge, required repeatedly so one stray line is not it;
#   4. no restart happened in the last REJOIN_RATE_LIMIT_SEC seconds (a stamp
#      file) — one restart per cooldown, so a genuinely broken agent becomes a
#      slow, visible restart loop rather than an unbounded hammer.
# When all hold: remove the node-password (k3s recreates it; a stale one can
# itself block re-registration) and restart the agent, then stamp. Otherwise it
# exits 0 quietly — the healthy case is the common case and must not spam the
# journal every minute.
#
# Every input is an env override so the whole decision is assertable off-host
# (./install-agent-rejoin-watchdog-exit-tests.sh drives it with fake
# systemctl/journalctl/date on PATH). It reads the journal, a TCP port and
# systemctl; it never touches the API server or a kubeconfig.
set -uo pipefail

NODE_NAME="${REJOIN_NODE_NAME:-$(hostname)}"
AGENT_UNIT="${REJOIN_AGENT_UNIT:-k3s-agent.service}"
CONFIG="${REJOIN_K3S_CONFIG:-/etc/rancher/k3s/config.yaml}"
NODE_PASSWORD="${REJOIN_NODE_PASSWORD:-/etc/rancher/node/password}"
STAMP="${REJOIN_STAMP:-/run/agent-rejoin-watchdog.last-restart}"
WINDOW_SEC="${REJOIN_WINDOW_SEC:-180}"
MIN_HITS="${REJOIN_MIN_HITS:-5}"
RATE_LIMIT_SEC="${REJOIN_RATE_LIMIT_SEC:-300}"
TCP_TIMEOUT="${REJOIN_TCP_TIMEOUT:-5}"

log() { printf '%s agent-rejoin-watchdog: %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*" >&2; }

# GATE 1 — the process must be up. A down agent is Restart=always's job, not
# this watchdog's; acting here would race that and could restart during systemd's
# own restart backoff.
if ! systemctl is-active --quiet "${AGENT_UNIT}"; then
  exit 0
fi

# The control-plane address the agent was told to join, read from its own config
# rather than hardcoded, so a re-homed cluster needs no edit here. `server:
# https://host:port` -> host and port; the port defaults to k3s's 6443.
server_line="$(awk -F'server:[[:space:]]*' '/^[[:space:]]*server:/ {print $2; exit}' "${CONFIG}" 2>/dev/null | tr -d '"'\''[:space:]')"
if [ -z "${server_line}" ]; then
  # No server line means this is not a joined agent (or the config moved); there
  # is nothing to rejoin to, so there is nothing to do.
  exit 0
fi
host_port="${server_line#*://}"
server_host="${host_port%%:*}"
server_port="${host_port##*:}"
[ "${server_port}" = "${host_port}" ] && server_port=6443

# GATE 2 — the API server must answer on its port. A restart cannot rejoin to a
# server that is down; if it is unreachable this is an outage to wait out, not a
# wedge to repair. `timeout` wraps the bash /dev/tcp connect so the whole probe
# is one fakeable command in the tests.
if ! timeout "${TCP_TIMEOUT}" bash -c ": < /dev/tcp/${server_host}/${server_port}" 2>/dev/null; then
  exit 0
fi

# GATE 3 — the wedge signature, counted over the window. grep -c exits non-zero
# on zero matches; `set -uo` (no -e) lets the count land as 0 and the script go
# on. The needle is exactly what k3s logs when the Node object is gone.
since="$(date '+%Y-%m-%d %H:%M:%S' -d "-${WINDOW_SEC} seconds" 2>/dev/null)"
hits="$(journalctl -u "${AGENT_UNIT}" --since "${since}" --no-pager 2>/dev/null \
        | grep -c -F "node \"${NODE_NAME}\" not found")"
hits="${hits:-0}"
if [ "${hits}" -lt "${MIN_HITS}" ]; then
  exit 0
fi

# GATE 4 — one restart per cooldown. If we restarted within the window, the last
# restart has not had time to take effect; a fresh restart now would be the
# hammer this watchdog exists to avoid.
now="$(date +%s)"
if [ -f "${STAMP}" ]; then
  last="$(stat -c %Y "${STAMP}" 2>/dev/null || printf '0')"
  if [ $((now - last)) -lt "${RATE_LIMIT_SEC}" ]; then
    log "wedge signature present (${hits} hits) but a restart happened $((now - last))s ago (< ${RATE_LIMIT_SEC}s cooldown) — holding"
    exit 0
  fi
fi

log "WEDGED: ${AGENT_UNIT} is active, ${server_host}:${server_port} is reachable, and the agent journal shows 'node \"${NODE_NAME}\" not found' ${hits}x in the last ${WINDOW_SEC}s — removing the node-password and restarting the agent to force re-registration"
# The node-password can itself block a rejoin when the server's record of it was
# lost with the datastore; k3s recreates it on the next start. Removing a missing
# file is not an error.
rm -f "${NODE_PASSWORD}"
if systemctl restart "${AGENT_UNIT}"; then
  # Stamp only on a restart that was actually issued, so the cooldown measures
  # real restarts rather than attempts.
  : > "${STAMP}" 2>/dev/null || true
  log "restarted ${AGENT_UNIT}; the agent should re-register within ~1-2 minutes (verify: kubectl get node ${NODE_NAME} on the server)"
  exit 0
fi

log "FAILED to restart ${AGENT_UNIT} — leaving the cooldown stamp untouched so the next tick retries"
exit 1

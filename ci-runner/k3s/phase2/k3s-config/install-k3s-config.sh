#!/usr/bin/env bash
# install-k3s-config.sh — install the fleet's k3s configuration for THIS node's
# ROLE to /etc/rancher/k3s/config.yaml on a CI runner pool NODE: ./config.yaml
# on a server, ./config.agent.yaml on an agent. On a server it also writes the
# packaged-component skip marker for the bundled local-path provisioner; on an
# agent it writes no marker and removes one it finds.
#
# WHY THIS EXISTS: until 2026-09-02 the host's config.yaml was hand-written
# (kubelet max-pods=200, livespec-a6lxuv) and lived nowhere in git — durable
# across a reboot, lost on a rebuild. This installer makes the shipped copy the
# source of truth and the live file its output (the recreatability rule every
# sibling installer follows: edit the source, re-run, never the live file).
#
# ROLE-AWARE (2026-09-07, livespec-dev-tooling-vcv4, livespec plan
# `k3s-on-gmktec-for-vps-usage` carrier R3). Until now this installed
# ./config.yaml on whatever node ran it, and ../install-node.sh runs it on BOTH
# roles. That file carries two SERVER-ONLY keys, and an agent handed them does
# not ignore them: k3s-agent exits `level=fatal ... flag provided but not
# defined: -disable` and systemd restart-loops the unit. Measured on
# gmktec-xubuntu 2026-09-07 — and measured only then, because a config is read
# at the NEXT k3s start, so several earlier runbook runs had installed it with
# nothing to show for it until the first restart. ./config.agent.yaml's header
# names each absent key and why. ../../provision-k3s.sh's step 0 already drew
# the same boundary from its side by SKIPping its k3s-config step on an agent.
#
# TWO ENFORCEMENT POINTS FOR ONE DISABLE, ON A SERVER: `disable: [local-storage]`
# in the config file tells k3s not to deploy its bundled provisioner; the
# `local-storage.yaml.skip` marker in the packaged-manifests directory is k3s's
# documented per-manifest opt-out and holds independently of how config-file and
# command-line `--disable` values are merged. Both are written so the
# fleet-owned provisioner (../local-path-provisioner/) can never be overwritten
# by the bundled copy. The marker directory is under
# /var/lib/rancher/k3s/server/ (on disk, NOT the tmpfs datastore), so it is
# reboot-durable — and it is a SERVER path, which is why an agent gets neither
# enforcement point: it deploys no packaged components to disable.
#
# TAKES EFFECT ON THE NEXT k3s START. This installer never restarts k3s or
# k3s-agent, INCLUDING when it has just replaced a server config found on an
# agent: a restart kills every running CI job on the pool, so it is done at zero
# active jobs, by the runbook's later steps, by the operator, or by a reboot
# (the reconstruct-on-boot path re-applies the fleet-owned provisioner within
# the converge).
#
# NODE-LOCAL, like ../node-inotify-budget/install-inotify-sysctl.sh: re-run on
# any node added to the pool and after any node rebuild. Idempotent. Run it
# BEFORE ../../provision-k3s.sh on a fresh SERVER so the first k3s start already
# reads it.
#
# Usage: sudo install-k3s-config.sh [--role server|agent]
#   --role  the node's cluster role, which selects the file installed and
#           whether the skip marker is written. ../install-node.sh passes the
#           role it read from the node's profile, so the role a step installs
#           for is the role the profile declares rather than one typed at a call
#           site. Defaults to the CLUSTER_ROLE environment variable, then to
#           `server` — what a bare invocation meant before this script knew
#           about roles, and what ../../provision-k3s.sh's own (server-only)
#           call site still means by it.
#
# Requires: root (writes /etc/rancher/k3s and, on a server,
# /var/lib/rancher/k3s/server).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_NAME="$(basename "$0")"

# TEST ROOT — empty on a node, and the ONLY way this script can be aimed at
# anything but the real host. Every absolute path below is resolved under it, so
# ./install-k3s-config-exit-tests.sh can build a node that already carries the
# wrong role's config inside a scratch directory and assert what a run does to
# it. It is never set on a node, and ../install-node.sh never sets it. Same
# shape as STORAGE_LAYOUT_ROOT in ../storage-layout/install-storage-layout.sh.
ROOT="${K3S_CONFIG_ROOT:-}"
ROOT="${ROOT%/}"

SERVER_SRC="${SCRIPT_DIR}/config.yaml"
AGENT_SRC="${SCRIPT_DIR}/config.agent.yaml"
CONFIG_DST="${ROOT}/etc/rancher/k3s/config.yaml"
MANIFESTS_DIR="${ROOT}/var/lib/rancher/k3s/server/manifests"
SKIP_MARKER="${MANIFESTS_DIR}/local-storage.yaml.skip"

# The keys ./config.yaml carries that ./config.agent.yaml deliberately does not.
# Named here so a server config found on an agent is reported by WHAT makes it
# wrong rather than by its filename — the operator reading the replacement has
# to see the key that was about to kill k3s-agent.
SERVER_ONLY_KEYS=(disable write-kubeconfig-mode)

USAGE="usage: sudo ${SCRIPT_NAME} [--role server|agent]   (--role defaults to \$CLUSTER_ROLE, then to server)"

die() { printf 'FATAL: %s\n' "$*" >&2; exit 1; }
log() { printf '\n== %s ==\n' "$*"; }

# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------
ROLE=""
ROLE_GIVEN=0

while [ $# -gt 0 ]; do
  case "$1" in
    --role)
      [ $# -ge 2 ] || die "--role needs a value -- ${USAGE}"
      [ -n "$2" ] || die "--role needs a value -- ${USAGE}"
      [ "$ROLE_GIVEN" -eq 0 ] || die "--role given more than once -- ${USAGE}"
      ROLE_GIVEN=1
      ROLE="$2"; shift ;;
    -h|--help) printf '%s\n' "$USAGE"; exit 0 ;;
    -*) die "unknown option '$1' -- ${USAGE}" ;;
    *) die "unexpected argument '$1' -- ${USAGE}" ;;
  esac
  shift
done

ROLE="${ROLE:-${CLUSTER_ROLE:-server}}"
case "$ROLE" in
  server) CONFIG_SRC="$SERVER_SRC" ;;
  agent)  CONFIG_SRC="$AGENT_SRC" ;;
  *) die "role must be 'server' or 'agent', got '${ROLE}'" ;;
esac

# config_keys FILE -> the file's top-level YAML keys, one per line, in order.
# A shallow reader on purpose: these files are flat key/list documents, and what
# the operator needs from a replacement is which KEYS changed — the values are
# in the diff printed under it.
config_keys() { sed -n 's/^\([A-Za-z][A-Za-z0-9_-]*\):.*$/\1/p' "$1"; }

printf '== %s plan ==\n' "$SCRIPT_NAME"
printf 'role:    %s\n' "$ROLE"
printf 'source:  %s\n' "$CONFIG_SRC"
printf 'dest:    %s\n' "$CONFIG_DST"
if [ "$ROLE" = server ]; then
  printf 'marker:  %s (written)\n' "$SKIP_MARKER"
else
  printf 'marker:  %s (NOT written on an agent; removed if present)\n' "$SKIP_MARKER"
fi
if [ -n "$ROOT" ]; then
  printf 'root:    %s   (K3S_CONFIG_ROOT -- TEST USE ONLY; never set on a node)\n' "$ROOT"
fi

[ "$(id -u)" -eq 0 ] || die "must run as root (writes ${CONFIG_DST} and, on a server, ${MANIFESTS_DIR})"
[ -f "$CONFIG_SRC" ] || die "shipped ${ROLE} config not found at ${CONFIG_SRC}"

# ---------------------------------------------------------------------------
log "1. Install ${CONFIG_DST} from the shipped ${ROLE} copy"
if [ -f "$CONFIG_DST" ] && cmp -s "$CONFIG_SRC" "$CONFIG_DST"; then
  echo "${CONFIG_DST} already matches the shipped ${ROLE} copy — unchanged"
else
  if [ -f "$CONFIG_DST" ]; then
    # The one replacement that is a REPAIR rather than a refresh: an agent
    # carrying the server file. Named as such, and by the offending KEYS, because
    # the operator reading this line is reading the fix for a k3s-agent restart
    # loop and needs to recognise the state it fixes.
    if [ "$ROLE" = agent ]; then
      # Matched with bash's own `case` against a newline-delimited string rather
      # than `config_keys ... | grep -q`: `grep -q` exits at the first match and
      # SIGPIPEs the producer, and under `pipefail` that 141 is the pipeline's
      # status — so the key that WAS found would be read as absent.
      live_keys=$'\n'"$(config_keys "$CONFIG_DST")"$'\n'
      found_server_only=""
      for server_only_key in "${SERVER_ONLY_KEYS[@]}"; do
        case "$live_keys" in
          *$'\n'"${server_only_key}"$'\n'*)
            found_server_only="${found_server_only}${found_server_only:+ }${server_only_key}" ;;
        esac
      done
      if [ -n "$found_server_only" ]; then
        echo "REPAIR: ${CONFIG_DST} on this AGENT carries SERVER-ONLY key(s): ${found_server_only}"
        echo "        with these present k3s-agent exits 'flag provided but not defined: -disable' at its next start (livespec-dev-tooling-vcv4)"
      fi
    fi
    echo "replacing ${CONFIG_DST}; top-level keys (live -> shipped ${ROLE}):"
    printf '  live:    %s\n' "$(config_keys "$CONFIG_DST" | paste -sd' ' -)"
    printf '  shipped: %s\n' "$(config_keys "$CONFIG_SRC" | paste -sd' ' -)"
    echo "diff (live -> shipped):"
    diff "$CONFIG_DST" "$CONFIG_SRC" || true
  fi
  install -d -m 0755 "$(dirname "$CONFIG_DST")"
  install -m 0600 "$CONFIG_SRC" "$CONFIG_DST"
  echo "installed ${CONFIG_DST} (takes effect on the next k3s start)"
fi

# ---------------------------------------------------------------------------
if [ "$ROLE" = agent ]; then
  log "2. [agent] NO packaged-manifest skip marker — ${MANIFESTS_DIR} is a SERVER path"
  if [ -e "$SKIP_MARKER" ]; then
    rm -f "$SKIP_MARKER"
    echo "removed ${SKIP_MARKER} (left by an earlier server-config run; an agent deploys no packaged component to disable)"
  else
    echo "no marker present — nothing to remove"
  fi
else
  log "2. Write the packaged-manifest skip marker ${SKIP_MARKER}"
  install -d -m 0700 "$MANIFESTS_DIR"
  if [ -e "$SKIP_MARKER" ]; then
    echo "${SKIP_MARKER} already present"
  else
    : > "$SKIP_MARKER"
    chmod 0600 "$SKIP_MARKER"
    echo "wrote ${SKIP_MARKER}"
  fi
fi

# ---------------------------------------------------------------------------
log "3. Report the running k3s's view (informational)"
if [ "$ROLE" = server ]; then
  if [ -e "${MANIFESTS_DIR}/local-storage.yaml" ]; then
    echo "NOTE: the bundled ${MANIFESTS_DIR}/local-storage.yaml is still present — k3s removes it on its next start"
  else
    echo "bundled local-storage.yaml absent — the disable is in effect"
  fi
  K3S_UNIT=k3s.service
else
  K3S_UNIT=k3s-agent.service
fi
if systemctl is-active --quiet "$K3S_UNIT" 2>/dev/null; then
  echo "${K3S_UNIT} is running: the new config applies on its NEXT start (do that at zero active CI jobs, or by reboot)"
fi

if [ "$ROLE" = agent ]; then
  log "DONE. Agent k3s config installed; no server-only key and no packaged-manifest marker on this node."
else
  log "DONE. k3s config installed; local-storage disabled at two enforcement points."
fi

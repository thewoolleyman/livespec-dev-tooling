#!/usr/bin/env bash
# Runs ON the guest as its own transient unit, so injections land within ~20 ms
# of the event (a rollback's eight phases complete in about 4 s, far inside
# one ssh round trip). Usage: guest_inject.sh <mode> <phase|-> <run>
MODE=$1 PH=$2 RUN=$3 G=/var/lib/docker-engine-guard/runs/$3 LOG=/run/fault-inject-$3.log
log() { echo "$(date -u +%T.%3N) $*" >> "$LOG"; }
child() { for p in $(pgrep -f "docker_engine_guard.py rollback $RUN .*--phase $PH\$"); do a=$(tr '\0' ' ' </proc/$p/cmdline 2>/dev/null); case $a in timeout*|"") ;; *) echo "$p"; return ;; esac; done; }
driver() { for p in $(pgrep -f "docker_engine_guard.py rollback $RUN"); do a=$(tr '\0' ' ' </proc/$p/cmdline 2>/dev/null); case $a in *--phase*|timeout*|"") ;; *) echo "$p"; return ;; esac; done; }
end=$((SECONDS + 1800)); log "armed $MODE $PH"
case $MODE in
  kill|hang)
    while [ $SECONDS -lt $end ]; do c=$(child); if [ -n "$c" ]; then
      if [ "$MODE" = kill ]; then kill -KILL "$c"; else kill -STOP "$c"; fi; log "$MODE $PH child $c"; exit 0; fi; sleep 0.02; done ;;
  deadman)
    while [ $SECONDS -lt $end ]; do n=$(ls "$G/rollback" 2>/dev/null | grep -c '\.success$'); if [ "$n" -ge 2 ]; then
      systemctl kill -s KILL "docker-engine-deadman-$RUN.service"; log "killed dead-man service after $n phase successes"; exit 0; fi; sleep 0.01; done ;;
  parent)
    k=0; while [ $SECONDS -lt $end ]; do
      if [ -n "$(child)" ]; then d=$(driver); if [ -n "$d" ]; then kill -KILL "$d"; k=$((k+1)); log "kill#$k driver $d in $PH (attempts $(cat "$G/rollback/$PH.attempts" 2>/dev/null))"; sleep 1; fi; fi
      case $(cat "$G/phase" 2>/dev/null) in rolled-back|rollback-partial) [ $k -ge 1 ] && { log "phase $(cat "$G/phase") after $k kills"; exit 0; } ;; esac
      sleep 0.02; done ;;
  respawn)
    while [ $SECONDS -lt $end ]; do
      if [ ! -e /run/docker-engine-guard/allow-start ]; then m=$(systemctl show -p MainPID --value docker.service)
        if [ "${m:-0}" != 0 ]; then kill -KILL "$m"; log "SIGKILLed dockerd $m after the revoke"
          for _ in $(seq 1 40); do log "docker.service=$(systemctl is-active docker.service) docker.socket=$(systemctl is-active docker.socket) NRestarts=$(systemctl show -p NRestarts --value docker.service)"; sleep 0.25; done; exit 0; fi; fi
      sleep 0.005; done ;;
  race-confirm-first)
    # C-01: the dead-man's service starts the instant the controller's confirm unit appears.
    while [ $SECONDS -lt $end ]; do
      if systemctl list-units --plain --no-legend "docker-engine-guard-confirm-$RUN-*" | grep -q .; then
        systemctl start --no-block "docker-engine-deadman-$RUN.service"; log "confirm unit seen; dead-man service started"; exit 0; fi
      sleep 0.005; done ;;
  race-deadman-first)
    # C-01, other order: the dead-man's service starts the instant the run reads `observed`, before the controller's confirm.
    while [ $SECONDS -lt $end ]; do
      if [ "$(cat "$G/phase" 2>/dev/null)" = observed ]; then
        systemctl start --no-block "docker-engine-deadman-$RUN.service"; log "observed; dead-man service started ahead of confirm"; exit 0; fi
      sleep 0.005; done ;;
esac
log "TIMEOUT"

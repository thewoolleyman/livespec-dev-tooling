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
    while [ $SECONDS -lt $end ]; do n=$(find "$G/rollback" -maxdepth 1 -name '*.success' 2>/dev/null | wc -l); if [ "$n" -ge 2 ]; then
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
  sigstop)
    # C-03: SIGSTOP the main process of the first unit named <prefix> (PH is the
    # unit-name prefix), then time until systemd kills it and the lock frees.
    # RUN may be `-` when the run id is not yet known (reserve).
    while [ $SECONDS -lt $end ]; do
      u=$(systemctl list-units --plain --no-legend --state=active,activating "$PH*" | awk '{print $1}' | head -1)
      if [ -n "$u" ]; then m=$(systemctl show -p MainPID --value "$u")
        if [ "${m:-0}" != 0 ] && flock -n /run/docker-engine-guard/lock true 2>/dev/null; then sleep 0.005; continue; fi
        if [ "${m:-0}" != 0 ]; then kill -STOP "$m"; t0=$SECONDS; log "SIGSTOP $u main $m while it holds the lock; TimeoutStartSec=$(systemctl show -p TimeoutStartUSec --value "$u")"
          # deactivating counts as alive: SIGKILL may still be pending on the stopped process
          while case "$(systemctl show -p ActiveState --value "$u" 2>/dev/null)" in active|activating|deactivating|reloading) true;; *) false;; esac; do sleep 0.5; done
          log "$u ended after $((SECONDS - t0))s: $(systemctl show -p Result --value "$u" 2>/dev/null); main $m $( [ -d /proc/"$m" ] && echo ALIVE || echo gone)"
          # flock -n exits non-zero both on a conflict and on a failed open, so the conflict gets its own code
          flock -n -E 200 /run/docker-engine-guard/lock true 2>/dev/null; rc=$?
          case $rc in 0) log "lock released";; 200) log "LOCK STILL HELD";; *) log "lock released (lock file absent, rc=$rc)";; esac
          exit 0; fi; fi
      sleep 0.005; done ;;
  pause-observer)
    # C-09: SIGSTOP the observer's main process while the run is observing, start
    # the dead-man's service, wait for the rollback to end, then SIGCONT it. The
    # observer must be dead (the rollback stops its unit) and must write nothing.
    while [ $SECONDS -lt $end ]; do
      if [ "$(cat "$G/phase" 2>/dev/null)" = observing ]; then
        u=$(systemctl list-units --plain --no-legend --state=active,activating "docker-engine-guard-observe*" | awk '{print $1}' | head -1)
        m=$(systemctl show -p MainPID --value "$u" 2>/dev/null)
        if [ -n "$u" ] && [ "${m:-0}" != 0 ]; then kill -STOP "$m"; log "SIGSTOP observer $u main $m"
          systemctl start --no-block "docker-engine-deadman-$RUN.service"; log "dead-man service started"
          while case $(cat "$G/phase" 2>/dev/null) in rolled-back|rollback-partial) false;; *) true;; esac; do sleep 0.2; done
          before=$(stat -c %Y "$G/phase"); kill -CONT "$m" 2>/dev/null && log "SIGCONT sent to $m" || log "SIGCONT: $m already gone"
          sleep 5
          log "observer main $m $( [ -d /proc/"$m" ] && echo ALIVE || echo gone); unit $u $(systemctl is-active "$u" 2>/dev/null); phase $(cat "$G/phase") phase-file-touched-after-resume=$( [ "$(stat -c %Y "$G/phase")" -gt "$before" ] && echo YES || echo no)"
          exit 0; fi; fi
      sleep 0.01; done ;;
esac
log "TIMEOUT"

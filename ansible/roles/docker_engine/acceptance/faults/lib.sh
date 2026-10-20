# shellcheck shell=bash
# Shared helpers for the docker_engine FAULTS suite. Source from a case script.
cd "$(dirname "${BASH_SOURCE[0]}")/../../../../.." || exit 1
# WHICH MACHINE HOSTS THE VMs IS THE INVENTORY'S DECISION, NEVER THIS FILE'S — the
# same rule ansible/docker-engine-acceptance.yml states for its own play, and the
# reason the guest key the play fetches is named after inventory_hostname
# (livespec-dev-tooling-prdxxe). So the harness is TOLD, in one variable that
# ../inventory-kvm.yml reads from the same environment, and it refuses before it
# touches anything rather than guessing: pointed at the wrong machine, every case
# would fail at its first ssh with a connection error, which reads as a broken VM
# rather than as a harness nobody told where to run.
FAULTS_KVM_HOST="${DOCKER_ENGINE_ACCEPTANCE_KVM_HOST:?set this to the inventory name of the KVM acceptance host (the docker_engine_acceptance_hosts group member) before running a FAULTS case}"
# The login account on that host. A user is not a machine, so it stays a literal.
FAULTS_KVM_USER="${DOCKER_ENGINE_ACCEPTANCE_KVM_USER:-cwoolley}"
# Every driver writes its logs under tmp/faults (gitignored); a fresh worktree lacks it, and a
# missing directory made every converge redirect fail while the driver still exited 0.
mkdir -p tmp/faults || exit 1
FAULTS_KEY=$HOME/.cache/docker-engine-guard-acceptance/$FAULTS_KVM_HOST/id_ed25519
vm() { local i=$1; shift; ssh -i "$FAULTS_KEY" -o ProxyJump="$FAULTS_KVM_USER@$FAULTS_KVM_HOST" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o BatchMode=yes -o LogLevel=ERROR -p $((2229 + 10 * i)) guard@127.0.0.1 "$@"; }
converge() { # converge <i> <log> [extra ansible args...]
  local i=$1 log=$2; shift 2
  mise exec -- just ansible-apply -i ansible/roles/docker_engine/acceptance/inventory-kvm.yml ansible/docker-engine.yml --limit "guard-vm-$i" "$@" > "$log" 2>&1
  local rc=$?; echo "converge exit=$rc"; grep -A1 "PLAY RECAP" "$log" | tail -1
  grep -E "^\[ERROR\]|\"msg\":" "$log" | tail -3 | cut -c1-400
  return 0
}
footprint() { # footprint <i>: everything a refused converge must leave untouched
  vm "$1" 'sudo bash -c "
    echo pkgs: \$(dpkg-query -W -f=\"\${Package} \" docker.io containerd docker-ce runc 2>/dev/null; dpkg -l | grep -cE \"^ii\")
    echo guard-state: \$(ls -A /var/lib/docker-engine-guard 2>/dev/null | tr \"\n\" \" \" || echo none)
    echo guard-tree: \$(ls /usr/local/lib/docker-engine-guard 2>/dev/null | head -3 | tr \"\n\" \" \" || echo none)
    echo dropins: \$(ls /etc/systemd/system/{containerd,docker}.service.d /etc/systemd/system/docker.socket.d 2>/dev/null | tr \"\n\" \" \")
    echo var-lib-docker: \$(ls -A /var/lib/docker 2>/dev/null | tr \"\n\" \" \" || echo absent)
    echo forward: \$(iptables -S FORWARD | head -1) / \$(ip6tables -S FORWARD | head -1)
    echo docker0: \$(ip -o link show docker0 2>/dev/null | cut -d: -f2 || echo absent)
    echo units: \$(for u in k3s-agent tailscaled local-homelab-llama-server; do printf \"%s=%s \" \$u \$(systemctl is-active \$u.service); done)
    echo etc-docker: \$(ls -A /etc/docker 2>/dev/null | tr \"\n\" \" \" || echo absent)
  "'
}

# --- phase-keyed injection -------------------------------------------------
latest_run() { vm "$1" 'sudo bash -c "ls -t /var/lib/docker-engine-guard/runs 2>/dev/null | head -1"'; }
phase_of() { vm "$1" "sudo bash -c 'r=\$(ls -t /var/lib/docker-engine-guard/runs 2>/dev/null | head -1); [ -n \"\$r\" ] && cat /var/lib/docker-engine-guard/runs/\$r/phase'" 2>/dev/null; }
guard_op() { # guard_op <i> <op> <run> [extra args]: run one guard operation as the role does, print exit and journal
  local i=$1 op=$2 run=$3; shift 3
  vm "$i" "U=docker-engine-guard-$op-$run-fault-\$(date +%H%M%S%N | cut -c1-9); S=\$(date +%s); sudo systemd-run --unit=\$U --wait --collect --quiet --property=Type=oneshot --property=TimeoutStartSec=1900 /usr/local/libexec/docker-engine-guard $op $run --window-seconds=420 $*; echo \"$op $run exit=\$?\"; sudo journalctl -u \$U.service --since=@\$S --no-pager -o cat | grep -vE '^(Starting|Finished|docker-engine-guard-.*: (Deactivated|Main process|Failed))'"
}
# The k3s, flannel, kube-router and Tailscale chains, as FAULTS.md's "rolled back"
# compares them: every table of both families, counters stripped, Docker's own
# rules and chains left to the docker-chains count, and kube-router's per-pod
# chains and jumps dropped (they churn as pods come and go, measured on
# guard-vm-0 2026-10-18: KUBE-POD-FW-<hash> chains changed within 60 s at rest).
HOST_CHAINS_CMD='for f in iptables ip6tables; do for t in filter nat mangle raw; do $f-save -t $t 2>/dev/null | sed "s/\[[0-9]*:[0-9]*\]//" | grep -vE "^#|^\*|^COMMIT|DOCKER|docker0|KUBE-(POD-FW|SEP|SVC|EXT|FW|SVL)-|POD name:" | sed "s/^/$f $t /"; done; done | sort'
host_chains_save() { # host_chains_save <i>: record the pre-change host chains on the guest
  vm "$1" "sudo bash -c '$HOST_CHAINS_CMD > /var/tmp/faults-host-chains.before'"
}
host_chains_check() { # host_chains_check <i>: compare the host chains now with the recorded ones
  vm "$1" "sudo bash -c '$HOST_CHAINS_CMD > /var/tmp/faults-host-chains.after; if diff -q /var/tmp/faults-host-chains.before /var/tmp/faults-host-chains.after >/dev/null; then echo host-chains: equal \$(wc -l < /var/tmp/faults-host-chains.before) lines; else echo host-chains: DIFF; diff /var/tmp/faults-host-chains.before /var/tmp/faults-host-chains.after | head -20; fi'"
}
rolled_back_check() { # the FAULTS.md definition of "rolled back", as far as it is observable
  vm "$1" 'sudo bash -c "
    r=\$(ls -t /var/lib/docker-engine-guard/runs | head -1); echo run=\$r phase=\$(cat /var/lib/docker-engine-guard/runs/\$r/phase)
    echo permission: \$(ls /run/docker-engine-guard/allow-start 2>/dev/null || echo none)
    for u in containerd.service docker.service docker.socket; do echo \"\$u active=\$(systemctl is-active \$u) jobs=\$(systemctl list-jobs --no-legend \$u | wc -l)\"; done
    echo forward: \$(iptables -S FORWARD | head -1) / \$(ip6tables -S FORWARD | head -1)
    echo docker-chains-v4: \$(iptables -S | grep -cE \"DOCKER\") v6: \$(ip6tables -S | grep -cE \"DOCKER\")
    echo docker0: \$(ip -o link show docker0 2>/dev/null | cut -d: -f2 || echo absent)
    echo marker: \$(cat /var/lib/docker-engine-guard/confirmed 2>/dev/null || echo none)
  "'
  host_chains_check "$1"
}

# A restored snapshot's persistent apt timers fire on catch-up minutes after boot; on
# guard-vm-0 (2026-10-17 20:55:39) unattended-upgrade began reinstalling docker.io
# mid-case. Masking them keeps every dpkg action on the guest the guard's own.
restore() { # restore <i>: one instance back to the `baseline` snapshot, booted, k3s DNS answering, apt timers masked
  local i=$1
  ssh -o BatchMode=yes "$FAULTS_KVM_USER@$FAULTS_KVM_HOST" "cd ~/docker-engine-guard-acceptance && export DOCKER_ENGINE_VM_BASE_DIR=\$HOME/.cache/docker-engine-guard-vm DOCKER_ENGINE_VM_LLM_BIND=0.0.0.0 DOCKER_ENGINE_VM_INSTANCE=$i && ./vm.sh down >/dev/null && ./vm.sh restore baseline >/dev/null && ./vm.sh up >/dev/null && for n in \$(seq 1 60); do ./vm.sh ssh sudo k3s kubectl get pods -n kube-system --no-headers 2>/dev/null | awk '\$1 ~ /^coredns-/ && \$3 == \"Running\" {f=1} END {exit !f}' && break; sleep 5; [ \$n = 60 ] && { echo restore-$i-DNS-TIMEOUT; exit 1; }; done; ./vm.sh ssh sudo systemctl stop apt-daily.timer apt-daily-upgrade.timer >/dev/null 2>&1; ./vm.sh ssh sudo systemctl mask apt-daily.timer apt-daily-upgrade.timer >/dev/null 2>&1 || { echo restore-$i-APT-TIMER-MASK-FAILED; exit 1; }; for n in \$(seq 1 60); do ./vm.sh ssh sudo fuser /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock /var/lib/apt/lists/lock >/dev/null 2>&1 || { echo restored-$i; exit 0; }; sleep 5; done; echo restore-$i-APT-BUSY; exit 1" && host_chains_save "$i"
}

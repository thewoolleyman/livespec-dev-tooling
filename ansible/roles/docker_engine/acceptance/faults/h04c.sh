#!/usr/bin/env bash
# FAULTS H-04 with the role fix: the same injected state, converged again.
set -uo pipefail
cd "$(dirname "$0")/../../../../.." || exit 1
# shellcheck source=/dev/null
source <(sed -n "/^KEY=/,/^converge() {/p" ansible/roles/docker_engine/acceptance/faults/h04b.sh | sed '$d')
converge() {
  mise exec -- just ansible-apply -i ansible/roles/docker_engine/acceptance/inventory-kvm.yml ansible/docker-engine.yml --limit guard-vm-0 -e "$1" > "$2" 2>&1
  echo "exit=$?"; grep -A1 "PLAY RECAP" "$2" | tail -1
  grep -c "TASK \[docker_engine : Run guard operation reconfigure\]" "$2" | sed 's/^/reconfigure ran: /'
}
echo "######## before (injected state left by h04b)"; state
echo "######## converge with CFG2 and the fixed role"; converge "$CFG2" tmp/faults/h04c.converge.log; state
echo "######## the guard's own view: confirm on the committed run"
vm0 'R=$(sudo python3 -c "import json;print(json.load(open(\"/var/lib/docker-engine-guard/confirmed\"))[\"run\"])"); U=docker-engine-guard-confirm-$R-h04c-$(date +%H%M%S); S=$(date +%s); sudo systemd-run --unit=$U --wait --collect --quiet --property=Type=oneshot --property=TimeoutStartSec=420 /usr/local/libexec/docker-engine-guard confirm $R --window-seconds=420; echo "confirm exit=$?"; sudo journalctl -u $U.service --since=@$S --no-pager -o cat | grep -iE "confirm (finish|proceed|refuse)"'
echo "######## a further converge must change nothing (H-02 still holds)"; converge "$CFG2" tmp/faults/h04c.again.log

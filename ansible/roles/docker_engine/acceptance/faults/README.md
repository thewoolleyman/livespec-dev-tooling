# FAULTS.md case drivers

One script per case (or pair) of `../FAULTS.md`, run from the repository root
through the detached gate runner against the acceptance guests:

    export DOCKER_ENGINE_ACCEPTANCE_KVM_HOST=<the docker_engine_acceptance_hosts member>
    mise exec -- just gate-start -- bash ansible/roles/docker_engine/acceptance/faults/<case>.sh

`DOCKER_ENGINE_ACCEPTANCE_KVM_HOST` is the ONE place the harness learns which
machine hosts the VMs — `../inventory-kvm.yml` reads the same variable, so the
drivers and the converge they run agree by construction. Which machine it is
belongs to the fleet inventory and to nothing in this tree
(livespec-dev-tooling-prdxxe), so a driver run without it refuses and names it
rather than guessing. `DOCKER_ENGINE_ACCEPTANCE_KVM_USER` overrides the login
account on that host; it defaults to the one the fleet inventory reaches it as.

`lib.sh` holds the shared helpers: `vm <i>` (ssh to guard-vm-<i>), `converge`,
`restore <i>` (one instance back to `baseline`, k3s DNS answering), `phase_of`,
`guard_op` (one guard operation run as the role runs it), `footprint` and
`rolled_back_check`. Injections key on the run's phase file, so each case uses
the real role converge and acts at the phase it names.

Case logs are written under `tmp/faults/`, which is gitignored.

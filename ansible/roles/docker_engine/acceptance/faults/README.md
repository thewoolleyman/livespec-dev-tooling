# FAULTS.md case drivers

One script per case (or pair) of `../FAULTS.md`, run from the repository root
through the detached gate runner against the poweredge acceptance guests:

    mise exec -- just gate-start -- bash ansible/roles/docker_engine/acceptance/faults/<case>.sh

`lib.sh` holds the shared helpers: `vm <i>` (ssh to guard-vm-<i>), `converge`,
`restore <i>` (one instance back to `baseline`, k3s DNS answering), `phase_of`,
`guard_op` (one guard operation run as the role runs it), `footprint` and
`rolled_back_check`. Injections key on the run's phase file, so each case uses
the real role converge and acts at the phase it names.

Case logs are written under `tmp/faults/`, which is gitignored.

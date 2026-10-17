# `ansible/` — host provisioning for the legacy Ubuntu fleet

This tree provisions the four pre-Talos Ubuntu machines — `vps`,
`poweredge-xubuntu`, `gmktec-xubuntu`, `hp-xubuntu` — replacing the
home-grown installer/converge shell that grew across three repositories.

livespec work-item `livespec-sab5gn.4`; rationale, the estate inventory and
the phase plan are in `thewoolleyman/livespec` at
`plan/k3s-on-gmktec-for-vps-usage/research/004-ansible-migration-direction-2026-09-09.md`
and `.../005-ansible-migration-estate-inventory-2026-09-09.md`.

## The two commands

```bash
just ansible-drift ansible/gates-kubeconfig.yml   # reports; changes nothing
just ansible-apply ansible/gates-kubeconfig.yml   # converges
```

`ansible-drift` is `--check --diff`. It is the drift report, and it replaces
the bespoke `ci-runner/k3s/phase2/reconstruct/verify-installed-tree.sh`.
Run it before every apply. `just check` runs `check-ansible-lint` over this
tree, at ansible-lint's `production` profile.

## The two rules this tree lives under

**A Talos node must never appear in the inventory.** The long-term fleet is
Talos, Omni and Flux, and that fleet's machines have no shell for Ansible to
reach. An entry here for a machine Omni owns would give it two declared
owners. Read the header of `inventory/legacy.yml` before adding a host.
These four machines are a sunset substrate: when a machine's workload moves
to the Talos fleet, delete its entry rather than porting anything.

**Kubernetes desired state does not migrate into Ansible.** Kueue queues,
ARC scale sets, gate Jobs, RBAC, the provisioner, warm-cache, sccache and
crates-proxy stay as manifests and kustomizations under `../ci-runner/`,
shaped so Flux could reconcile them unchanged. A playbook may `kubectl
apply -k` them; it may not encode their ordering in tasks. What migrates
here is host glue: files, systemd units, sysctls, pinned downloads, and
host-side files rendered from cluster state.

## Playbooks run from committed source

Never from an installed copy on the target. A host once ran a converge
script from before the gates queue existed, exited `Result=success`, and the
queue never appeared — the defect that `verify-installed-tree.sh` was built
to detect and that running from source removes instead.

The control node is `vps`, which manages itself over a local connection and
reaches the other three over the tailnet as `cwoolley`. All four already
carry a modern Python interpreter and passwordless sudo, so no bootstrap
step is needed.

## Why `uvx` rather than a dependency group

Ansible is a tool this repository invokes, never a library it imports, and
`ansible-core` 2.21 requires Python 3.12 while this repository's floor is
3.10.16. Raising that floor is a fleet-wide decision about the shared
enforcement suite and has nothing to do with provisioning hosts. Both
versions are pinned exactly in the justfile recipes, which remain the single
source of truth for how the tool is invoked.

## The playbooks

| Playbook | Hosts | Migrated from |
|---|---|---|
| `ci-pool.yml` | `poweredge-xubuntu`, `gmktec-xubuntu`, `hp-xubuntu` | `ci-runner/k3s/phase2/install-node.sh` |
| `gates-kubeconfig.yml` | `vps` | `vps-info` `services/gates-kubeconfig/` |
| `fabro-hosts.yml` | `hp-xubuntu`, `vps` | `fabro-hosts` `services/` |
| `dev-host.yml` | `vps` | `vps-info` `services/` |
| `reboot-ci-server.yml` | `ci_pool`, and only the host its confirmation names | nothing — no committed artifact could reboot a pool node |
| `node-loss-drill.yml` | `ci_pool`, and only the AGENT host its confirmation names | nothing — no committed artifact could take a pool node's k3s agent down |
| `restart-k3s-agent.yml` | `ci_pool`, and only the AGENT host its confirmation names | nothing — no committed artifact could restart a pool agent's k3s agent |

`reboot-ci-server.yml` is the ONE sanctioned way to reboot the k3s server, and
the only play here that reboots a host. It is an ordinary
`just ansible-apply ansible/reboot-ci-server.yml -e
ci_server_reboot_confirm=poweredge-xubuntu`, and without that confirmation
variable — naming the host's own inventory entry — it reads nothing, changes
nothing and exits 0, on an apply and under `--check` alike. That variable, not
omission from a sweep's argument list, is what keeps it out of every other
apply and every drift report. It waits for an idle `arc-runners` pool over two
consecutive reads and REFUSES rather than forcing a reboot through a busy one,
and it runs nothing after the reboot, because the unattended recovery is the
property a reboot drill exists to prove. See
`../ci-runner/k3s/README.md` §"Rebooting the k3s server" and
`livespec-dev-tooling-a3uvyu`.

`node-loss-drill.yml` is the ONE sanctioned way to take a pool AGENT node's
k3s agent down, hold the node NotReady for a configured window, and bring it
back — the committed path the `kubernetes-sandbox-backend` lifecycle proof
needs, which previously existed only as an `ssh … systemctl stop k3s-agent`
the Driver's fleet-host guard correctly refuses. It is an ordinary
`just ansible-apply ansible/node-loss-drill.yml -e
node_loss_drill_confirm=gmktec-xubuntu -e node_loss_drill_hold_minutes=5`, and
it shares `reboot-ci-server.yml`'s fence exactly: without a confirmation naming
the host's own inventory entry it reads nothing and changes nothing. Consent is
not sufficient, though — it REFUSES, loudly, a confirmation that names the
pool's control plane (reboot that with `reboot-ci-server.yml` instead) or any
member of `sandbox_hosts`, since a Fabro factory host runs the very server and
sandbox plugin the drill is being run for. Both sets come from the inventory,
so the refusal follows the groups through the Fabro cutover rather than a name.

Before the agent goes down it waits for the target to carry no `arc-runners`
runner pod and no `gates` Job pod, read twice and field-selected to that node
alone. It never cordons the node and never moves or removes a pod: a factory
sandbox pod on the target is the drill's SUBJECT, and taking it away answers a
different question. The restore lives in an `always:`, so a failed hold still
ends with the agent back up; the play then re-reads the node and FAILS unless
its taints, its `ci-runner.io/factory` label and its `ci-runner.io/churn-slot`
capacity are what they were, and reports the UTC instants at which the API
first showed the node NotReady and showed it Ready again. A `--check` run stops
after the idle read and the recorded posture, and says so. See
`livespec-dev-tooling-raynnh`.

`restart-k3s-agent.yml` is the ONE sanctioned way to restart a pool AGENT's
`k3s-agent`, which is how that agent's committed START configuration — its node
taints, its data-directory ordering, and above all its own `kubelet-arg+`
reservations — actually takes effect. `roles/k3s_config` renders all of it and
restarts nothing on purpose, so the rendered file is an opinion until the next
k3s start: on `hp-xubuntu` the reservations were written at 19:38 PDT
2026-10-13 over an agent running since 19:19, and the live node kept reporting
allocatable `cpu=16`, `memory=32176236Ki` for a node whose coexistence budget
reserves nearly all of it. `reboot-ci-server.yml` reboots the SERVER, and
`hp-xubuntu` is the Fabro factory host, so neither a reboot nor a hand
`systemctl restart` over ssh was available. It is an ordinary
`just ansible-apply ansible/restart-k3s-agent.yml -e
restart_k3s_agent_confirm=hp-xubuntu`, and it shares the fence above exactly:
without a confirmation naming the host's own inventory entry it reads nothing
and changes nothing, on an apply and under `--check` alike. It ADMITS agents
rather than excluding the server — the predicate is `cluster_role == 'agent'`,
so the control plane and any entry whose role is missing or misspelled are
refused loudly — and it does NOT refuse `sandbox_hosts`, because the factory
host is the node this playbook exists for.

What protects a factory host here is the pod gate, not a group refusal: one
read, field-selected to the target across every namespace, and the play REFUSES
— naming each pod — if the node is running anything a DaemonSet does not own. A
finished pod and a DaemonSet's pod are not workload; a bare pod is, which is
what a Fabro sandbox holding a run looks like. Unlike its two siblings it does
not wait, because the workload it finds is an operator's decision (drain the
run, or come back) rather than a CI job that finishes on its own. It then
restarts the unit, waits for the API to report the node Ready again, and prints
the node's capacity beside its allocatable so the apply's own output is the
evidence the reservations took effect. A `--check` run performs the pod read,
says the restart is withheld, and stops. See `livespec-dev-tooling-mbj3kz` and
`roles/docker_sandbox_slice/HOST_VARS.md` §"Coexistence with the k3s agent".

`ci-pool.yml` is the k3s pool's node-local provisioning — the roles
`install-node.sh` drove, in that step order, role-aware by each node's
`cluster_role`. It also carries the two steps that had no role
(`agent_rejoin`, `secret_reinjection`) and the churn-slot credential and
taint reconciliation (`node_status_credential`, `node_taints`) the R5
per-node model needs, and the server-side, evidence-gated repair of an agent's
stale k3s node-password secret (`agent_node_password`). Until it landed, no
playbook targeted `ci_pool`, so `poweredge-xubuntu` and `gmktec-xubuntu`
drifted unreached
(`livespec-dev-tooling-9btv`).

It also carries the FACTORY label's declarative reconcile (`node_labels`), which
sits beside `node_taints` and for the same reason: k3s applies `--node-label` at
node REGISTRATION only, so the label `provision-k3s.sh` registers at join is gone
the next time the cluster's objects are re-created. Every `ci_pool` node runs it,
the SERVER included — `poweredge-xubuntu` is a factory node and is untainted,
which is why "the factory nodes" could not be spelled as "the tainted ones".

**Three gating axes, not one.** `cluster_role` answers "server or agent".
`hp-xubuntu` is the first node for which that is not the whole question: it is a
Fabro FACTORY host that joins the pool as a full agent and executes **no CI
job**, carrying none of the pool's CI storage tiers. That posture is read from
the node's own committed phase0 profile (`CI_NODE_FACILITIES`, whose `none` the
profile parser refuses unless the profile *also* declares no tier,
`ADMISSION_CAPACITY_C=0` and a `node-role/ci` taint), and the four roles whose
whole subject is a CI tier or a CI job's execution environment —
`storage_layout`, `sccache_binary`, `cache_telemetry`, `container_hook` — are
gated on it with a `when:` in this one play rather than in a second play. Read
`ci-pool.yml`'s header for the three roles a closed node still runs and why each
one, and `tests/livespec_dev_tooling/test_ci_pool_factory_only_agent_roles.py`
for the test that resolves the whole answer from the inventory and the profiles.

The third axis is `FACTORY_NODE`, and it asks a question neither of the other two
can: **can this node take a factory pod?** All three nodes answer `true` — the
server included, which is why it is not `cluster_role`, and `hp-xubuntu` answers
it while executing no CI job, which is why it is not `CI_NODE_FACILITIES`.
`factory_workspace_root` is gated on it: the kubernetes-sandbox-backend plugin
takes ONE `workspace_root`, so every node that advertises factory capacity must
already carry a directory at that one absolute path
(`/srv/factory-workspaces`, `root:root` mode 0755, on a persistent non-tmpfs
filesystem the role measures at every apply). The capacity reasoning sits beside
the role in `roles/factory_workspace_root/CAPACITY.md`, and
`tests/livespec_dev_tooling/test_factory_workspace_root_provisioning.py` resolves
the host set from the same two inputs.

`ci_converge_unit` only ENABLES `converge-ci-stack.service` for the next boot; to
apply a committed change to the cluster stack now, pass `-e
ci_converge_unit_run_now=true` on one `just ansible-apply ansible/ci-pool.yml`
(it starts the converge, waits for it, and fails unless it succeeded).

`factory_reach_check` takes the same consent shape, and right after it in the
play. It installs `../ci-runner/k3s/phase2/factory/verify-factory-reach.sh`, the
probe it embeds and its two configuration files into the converge's installed
tree on the server, and measures nothing by default. To RUN the proof, pass `-e
factory_reach_check_run_now=true` on one apply: it submits a short-lived Job per
covered node, reports each node's exit code and the probe's own verdict line,
and refuses the apply unless every node reached every endpoint. The covered set
is every `ci_pool` node whose profile declares `FACTORY_NODE=true`; narrow it
with `-e '{"factory_reach_check_nodes": ["hp-xubuntu"]}'`. The run authenticates
as the `factory` namespace's scoped `sandbox-launcher` credential
(`/etc/ci-runner/factory.kubeconfig`, which `converge-ci-stack.sh` step 10e
renders here at every boot) and NEVER as the admin kubeconfig — a reach proved as
cluster admin is the reach of a credential no factory pod holds. Absent that
file the role refuses and names the converge that renders it, rather than
falling back (freeze ruling R70, `livespec-dev-tooling-jvnqwv`).

Roles live one per replaced service, named for the service with hyphens
becoming underscores. Each carries its own `defaults/main.yml`; values that
genuinely vary by machine live in `inventory/host_vars/<host>.yml` rather than
in a role, so a role never has to ask which host it is running on.

## Preconditions are asserted, not provisioned

Nineteen steps across the two host-record repositories are things an installer
refuses without and does not create: a built binary, a generated token file, a
private key loaded into a vault, a `tailscale serve` mapping owned by another
repository, a package the installer expects to already be there. None of them
migrate. Each becomes a preflight assertion at the top of its role, naming what
the operator must do and where, so a first apply on a rebuilt host fails at the
start rather than halfway through.

A few cannot be observed from the target host at all, such as a mapping in
another repository's state. Those are named in comments rather than faked as
checks.

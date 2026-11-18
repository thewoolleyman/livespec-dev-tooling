# `admin_kubeconfig` — a session account's cluster-admin kubeconfig

**What it is for.** A host that runs a coordinator, dispatcher or converge needs
`kubectl` against the cluster. Before this role the vps fell back to
`localhost:8080` and the coordinator read the cluster over ssh to the
control-plane node. This role installs the control-plane node's own admin
kubeconfig in the session account's `~/.kube/config`, with the loopback API
address rewritten to the node's tailnet name. Work-item
`livespec-dev-tooling-uf2pgj`.

**It is a cluster-admin credential.** Unlike `gates_kubeconfig` (the
`gate-submitter` ServiceAccount, jobs and pods in one namespace), this file can do
anything in the cluster. It is therefore 0600 in the account's own home, never in
the group-readable credential directory, and no task prints it. Add a host to the
`cluster_admin_hosts` group only after a second look at the credential path.

**The outage rule.** A control-plane outage must not break a converge on a host
that already holds the file: an unreachable node leaves the file untouched and the
play succeeds. A host that holds nothing and cannot reach the node fails, and says
so, so a first install never reports success with no credential. A node that
answers but returns a file that is not a kubeconfig with a client certificate and
key is refused before this host changes.

**Refresh.** The node renews its admin client certificate, so the installed file
goes stale when that happens. Refreshing is a re-run of the role (the playbook
`ansible/admin-kubeconfig.yml`, or the tag the consuming repository applies it
under): it reads the node again and replaces the file only if the content changed.

**What counts as an outage.** Any failure of the read keeps an existing file: a
connection that cannot be made, an ssh refusal, a non-zero `cat`, a file the node
does not have. Only a host with no file at all fails.

**Why a sibling and not one role.** `SPECIFICATION/contracts.md` names
`gates_kubeconfig` by role name for the delegated pre-push gate's credential, so
this stays a separate role. hetzner-xubuntu-info's `hxi_kubeconfig` consumes this
role instead of keeping a second copy.

## Variables

| variable | default | where set | meaning |
| --- | --- | --- | --- |
| `admin_kubeconfig_user` | `{{ ansible_user \| default('ubuntu') }}` | host_vars | the session account that holds the credential and runs kubectl |
| `admin_kubeconfig_remote_host` | the `ci_pool` member whose `cluster_role` is `server` | defaults | resolved from the inventory, never named |
| `admin_kubeconfig_fetch` | `slurp` | host_vars | `slurp` reads the file through the inventory, delegated to the control-plane node under become; `ssh` reads it over the session account's own ssh, as that account, with no privilege on the node, for a host with no inventory connection to it (set `admin_kubeconfig_remote_host` to the name its ssh client resolves) |
| `admin_kubeconfig_ssh_argv` | `[ssh, -o, BatchMode=yes]` | defaults | the ssh command the `ssh` fetch runs, before the node and `cat <path>` |
| `admin_kubeconfig_group` | the session user | defaults | the group of the credential |
| `admin_kubeconfig_remote_path` | `/etc/rancher/k3s/k3s.yaml` | defaults | where k3s writes the admin kubeconfig on that node |
| `admin_kubeconfig_dest` | `/home/<user>/.kube/config` | defaults | the credential on this host |
| `admin_kubeconfig_tailnet_domain` | `perch-rudd.ts.net` | defaults | the tailnet the API server is reached through |
| `admin_kubeconfig_api_port` | `6443` | defaults | the API server's port |
| `admin_kubeconfig_remote_become` / `admin_kubeconfig_become` | `true` / `false` | defaults | privilege for the read on the node, and for the local write |

`vps` is in the `cluster_admin_hosts` group and needs no per-host value: its
session account is `ubuntu`, the default.

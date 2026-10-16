# `factory_kubeconfig` — a Fabro-server host's `factory` namespace credential

**What it is for.** The Kubernetes sandbox backend launches a Fabro run's
sandbox pod in the cluster's `factory` Namespace, so the host running the Fabro
server needs a kubeconfig for that namespace's `sandbox-launcher`
ServiceAccount. The non-secret half of that identity is committed as
`ci-runner/k3s/phase2/factory/factory-rbac.yaml`
(`livespec-dev-tooling-f5e6vl`); this role delivers the rendered credential.
Work-item `livespec-dev-tooling-sqobqv`, livespec plan
`factory-worker-nodes-gitops` (epic `livespec-sqvj7p`).

**Why it is fetched rather than minted.** The control-plane node's k3s
datastore is a tmpfs (`ci-runner/k3s/phase2/datastore-tmpfs/`), so the
ServiceAccount and its token Secret are recreated at every boot and any
credential already on a host is stale from that moment.
`reconstruct/converge-ci-stack.sh` step 10e re-renders
`/etc/ci-runner/factory.kubeconfig` on the node at every boot; this role
fetches whatever is rendered now, and the two runtime tools it installs
re-fetch it on the first rejection after a reboot with no command run on any
host.

**The group play, never a host.** The role runs in `ansible/fabro-hosts.yml`'s
`sandbox_hosts` play. Every host that runs a Fabro server is reached through an
inventory GROUP (`livespec-dev-tooling-prdxxe`, enforced by `just
check-ansible-hostname-free`), so a factory host added to that group inherits
the credential and `livespec-dev-tooling-2puzjr`'s move of the live Fabro
server does not need this role edited.

## Variables

| variable | default | where set | meaning |
| --- | --- | --- | --- |
| `factory_kubeconfig_ssh_user` | `{{ ansible_user \| default('ubuntu') }}` | host_vars | the LOCAL login account whose tailnet ssh key reaches the control-plane node, and the account put in the credential's read group |
| `factory_kubeconfig_group` | `factory-client` | defaults (host_vars may override) | the dedicated group that may READ the credential |
| `factory_kubeconfig_kubectl_version` | `v1.36.2` | defaults | the cluster's k3s minor; co-maintained with `gates_kubeconfig_kubectl_version` |
| `factory_kubeconfig_dest` | `/etc/ci-runner/factory.kubeconfig` | defaults | the credential on this host |
| `factory_kubeconfig_remote_host` | the `ci_pool` member whose `cluster_role` is `server` | defaults | resolved from the inventory, never named |
| `factory_kubeconfig_remote_path` | `/etc/ci-runner/factory.kubeconfig` | defaults | where the converge renders it on that node |
| `factory_kubeconfig_refresh_env` | `/etc/ci-runner/factory-refresh.env` | defaults | where the runtime tools read this host's pool facts |
| `factory_kubeconfig_bin_dir` | `/usr/local/bin` | defaults | where kubectl and the two runtime tools land |

```yaml
# hp-xubuntu
factory_kubeconfig_ssh_user: cwoolley
```

`factory_kubeconfig_ssh_user` is the one value that genuinely varies by
machine, and it is stated explicitly for `hp-xubuntu` rather than left to the
default because getting it wrong is silent: the fetch would authenticate as an
account the tailnet ACL rejects on that host, which arrives as an ssh timeout
inside a refresh nobody is watching. The fleet's usual account is `ubuntu`;
this host's is `cwoolley`.

`factory_kubeconfig_group` is a fleet constant and stays in `defaults`, so
there is one place to change it. It is listed here because it is a legitimate
per-host override — a host whose Fabro server already runs under a different
reader group would set it — and it MUST NEVER be set to the gates group: the
two credentials grant different namespaces, and sharing one group would
silently widen each credential to the other's readers.

## The credential's shape, and why each part of it

Root-owned, `factory_kubeconfig_group`-readable, mode `0640`, written
atomically by a temp file and a rename.

- **Not root-only.** The Fabro server does not run as root, so a root-only
  credential is one the sandbox backend cannot read at all.
- **Not world-readable.** It is a bearer token for the whole `factory`
  namespace, on a host that also runs untrusted sandbox workloads.
- **The write stays root's.** A group member reads the token and cannot replace
  it. The runtime refresh reaches the file through the wrapper's `sudo -n`.
- **A temp file and a rename, not `install /dev/stdin DEST`.** uutils
  coreutils — what Ubuntu 25.10 and 26.04 ship — fails `install` whenever the
  destination already exists, which is exactly the state the refresh is called
  in (`livespec-dev-tooling-74q6iw`).

## The runtime tools

| tool | what it does |
| --- | --- |
| `with-factory-kubeconfig <cmd>…` | runs `<cmd>` against the credential; on the API server's rejection, refreshes ONCE through `sudo -n` and retries `<cmd>` once, re-feeding stdin when the argv named it |
| `refresh-factory-kubeconfig` | re-fetches the rendered file over this host's tailnet ssh identity and replaces the credential with the same owner, group and mode |

Both read their pool facts — the control-plane node, the ssh account and the
read group — from `factory_kubeconfig_refresh_env`, which this role writes from
the inventory. Neither script carries a hostname default: with no env-file they
refuse loudly rather than reaching for a machine that may no longer be the
cluster's server.

## Operator procedure

```bash
just ansible-drift ansible/fabro-hosts.yml     # read it
just ansible-apply ansible/fabro-hosts.yml
```

To converge only the credential after a control-plane rebuild, add
`--tags factory_kubeconfig`. A re-apply is the supported repair path: the
credential is re-fetched and rewritten, and nothing else on the host is
touched.

Verify on the host with the delivered credential:

```bash
with-factory-kubeconfig kubectl auth can-i create pods -n factory
```

## Retirement

Retire this role when the factory's sandbox pods move to the Talos fleet (see
the header of `inventory/legacy.yml`), whose machines expose no shell and whose
desired state is owned by Omni and Flux.

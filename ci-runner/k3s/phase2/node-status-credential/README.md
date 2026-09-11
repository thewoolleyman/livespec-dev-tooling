# node-status-credential — an AGENT node's churn-slot credential

## The defect this closes

`../node-extended-resource/reapply-node-extended-resource.service` patches a
node's `status.capacity` through the Kubernetes API. On a **server** its patch
script authenticates as the k3s server's admin kubeconfig,
`/etc/rancher/k3s/k3s.yaml`.

k3s writes that admin file on a server and **not on an agent**, so a node-local
churn-slot timer on an agent has no credential at all — its first fire fails.
Nothing under `ci-runner/` created such a credential and nothing placed one, so
there was no artifact that could have supplied it. (Since R5 the agent's patch
script authenticates with the kubeconfig THIS directory renders, at the path the
agent's profile names in `CHURN_KUBECONFIG_FILE` — see "The consumer, wired by
R5" below.)

Found by the first dry-run of the rebuild recipe on `gmktec-xubuntu`,
2026-09-06 (`livespec-dev-tooling-xa6o`, tree `b02cdb6e`). Re-verified from the
tree 2026-09-07 and again when this directory was authored.

## The obvious fix is the wrong one

Copying `/etc/rancher/k3s/k3s.yaml` onto the agent would work, and it would put
**unrestricted control of the whole cluster** on the pool's least-trusted
machine — the one that runs other people's CI jobs. This directory exists so
that nobody takes that shortcut for want of an alternative.

## What is here

| File | What it is |
| --- | --- |
| `node-status-patch-rbac.yaml` | The committed grant, as a template. A per-node ServiceAccount, a non-expiring token Secret, and a ClusterRole holding **exactly** `get`+`patch` on `nodes/status` with `resourceNames` naming one node. Never applied as it stands — `NODE_NAME_PLACEHOLDER` fails closed. |
| `provision-node-status-credential.sh` | The cluster-side converge, run **on the server** with the admin kubeconfig. Applies the RBAC for the node a profile names, then renders that ServiceAccount's kubeconfig. |
| `provision-node-status-credential-exit-tests.sh` | Proves the above off-cluster, off-host, with no credential. Its §B asserts the rule set **byte for byte**. |

The delivery half lives with the join token it copies, in
`../../secret-reinjection/seed-node-status-kubeconfig.sh` (and its own exit
tests). That is deliberate: a credential delivered by a second,
differently-shaped mechanism is a second mechanism to audit.

## Why the grant is narrower than it looks like it should be

One rule, two verbs, one named node:

```yaml
- apiGroups: [""]
  resources: [nodes/status]
  resourceNames: [<node>]
  verbs: [get, patch]
```

- **Not `nodes`.** The parent resource carries `spec`, and `patch` on it is
  enough to remove the node's own `node-role/ci=pending:NoSchedule` taint —
  which is the only thing keeping CI work off `gmktec-xubuntu` today (measured
  2026-09-08: its `status.capacity` already advertises `ci-runner.io/churn-slot:
  32`, the server's number, while its profile declares
  `ADMISSION_CAPACITY_C=0`). The status subresource cannot reach `spec`.
- **Not `list` or `watch`.** Kubernetes RBAC applies `resourceNames` only to
  requests that name a single object, so neither verb is restrictable at all;
  granting either would silently widen this from "one node" to "every node".
- **Not `delete`, and no wildcard.** A credential on a CI machine must not be
  able to evict the node from the cluster.

## The consumer, wired by R5

R5 (livespec plan `k3s-on-gmktec-for-vps-usage`, epic `livespec-sab5gn`,
resolving `livespec-dev-tooling-xa6o`) built the consumer this directory exists
to feed. `../node-extended-resource/patch-node-churn-capacity.sh` used to resolve
its targets with `kubectl get nodes -l k3s-role=arc-runner-host`, a **list** — so
it could not use this credential unchanged, and widening the credential to fit it
would have defeated the credential (the `list` bullet above). R5 made it patch a
**single named node** — the node its profile NAMES, `by name` — which is exactly
the shape `resourceNames` can authorize. So:

- `../node-extended-resource/install-reapply-unit.sh` now **installs on an
  agent** (it no longer refuses): it orders the reapply unit against
  `k3s-agent.service` and the patch script authenticates with the kubeconfig this
  credential renders, at the path the node's profile names in
  `CHURN_KUBECONFIG_FILE`.
- The patch script derives its credential from the profile's role — the server's
  admin kubeconfig, or, on an agent, the node-status kubeconfig this directory
  mints — so the unit carries no credential of its own.

**Which of the two options R5 chose.** The maintainer's 2026-09-07 ruling scoped
the per-node ServiceAccount shape this directory implements; a later measurement
raised a second option — leave node-status patches server-side and have the
server's timer read each node's `ADMISSION_CAPACITY_C`. R5 chose the FIRST (this
credential + a node-local agent timer), because the credential was already built
and reviewable and a node-local timer keeps each node's capacity a fact of its
own profile and its own systemd. The server's own timer is now scoped to the
server's OWN node (it no longer patches every labeled node), so the two nodes'
capacities never fight.

## Running it

Read the plan before minting anything. `--dry-run` needs no cluster, no root and
no credential, and prints the exact RBAC bytes it would apply:

```bash
ci-runner/k3s/phase2/node-status-credential/provision-node-status-credential.sh \
  --dry-run ci-runner/k3s/phase0-bare-metal/profiles/gmktec-xubuntu.env
```

Then, **on the server**, with `KUBECONFIG` pointing at the admin file:

```bash
sudo KUBECONFIG=/etc/rancher/k3s/k3s.yaml \
  ci-runner/k3s/phase2/node-status-credential/provision-node-status-credential.sh \
  --render-to /root/gmktec-node-status-kubeconfig \
  ci-runner/k3s/phase0-bare-metal/profiles/gmktec-xubuntu.env
```

The converge is idempotent (`kubectl apply --dry-run=client -o yaml -f - |
kubectl apply -f -`), so re-running changes nothing. Store the rendered file's
contents in the `github-ci-runners` 1Password Environment as
`K3S_NODE_STATUS_KUBECONFIG_CI_RUNNER`, delete it from the server, and seed it
onto the agent:

```bash
with-github-ci-runners-env.sh -- \
  ci-runner/k3s/secret-reinjection/seed-node-status-kubeconfig.sh \
  ci-runner/k3s/phase0-bare-metal/profiles/gmktec-xubuntu.env
```

It lands at the path that node's `CHURN_KUBECONFIG_FILE` names, mode `0600
root:root`.

## Rotation

`kubectl delete secret node-status-patcher-<node> -n ci-runner-node-status`,
re-run the provisioner, replace the 1Password value, re-run the seed. Nothing
here rotates on its own: a credential that rotated itself on an unattended timer
would need a second credential to do it with.

## Tests

```bash
ci-runner/k3s/phase2/node-status-credential/provision-node-status-credential-exit-tests.sh
ci-runner/k3s/secret-reinjection/seed-node-status-kubeconfig-exit-tests.sh
```

Neither needs a cluster, root, or a real credential.

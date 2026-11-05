> **Corrected in part, 2026-11-05:** §1's "ACL. No change is needed" was wrong: Tailscale distributes an approved subnet route only to devices the policy lets reach it, so a grant was added (tailscale-admin#42). See [008](008-lan-worker-and-test-strategy-2026-11-05.md) §2. The rest still holds.

# 006 — Tailnet identity and fixture-first corrections (2026-11-04)

Research notes are write-once, so this note corrects 005 rather than editing it. It changes three things: how the worker joins the
tailnet, the order of the egress-selector change, and where the first fixture runs.

## 1. No tags, no auth key: the worker is an untagged member

005 §3 ("Tailnet prerequisite", line 179) said the worker needs a `tag:homelab-worker` auth key, a `tagOwners` entry and a
restrictive ACL. 005 §3 (line 183) said the fixture VM joins with "an ephemeral tagged key". 005 §4 slice 4 said "Policy tags,
auth-key source". **All three are wrong for this tailnet.**

The maintainer pointed this out on 2026-11-04 ("Didn't we explicitly reject using tags and decide to make everything part of
default tailnet?"), and the tailscale-admin repository confirms it:

- `policy.hujson` has `"tagOwners": {}` and one grant, `autogroup:member` → `autogroup:member`, `ip ["*"]`.
- Tags were retired fleet-wide by maintainer ruling on 2026-08-17 (tailscale-admin `a7bd6d0`), after the flat tailnet was adopted
  (`43fc3c2`).
- `openspec/specs/acl-policy/constraints.md`: every persistent machine MUST be an untagged `autogroup:member`. No agent adds a
  tag, issuer, auth key or assignment without the maintainer's exact authorization.
- `auth-key-issuance`: the only approved enrollment route is interactive. The maintainer completes the login URL, and the device
  stays untagged. Tailscale lets OAuth-minted keys create only tagged devices, so the retained minting tool is not an approved
  route.

So:

- **Identity.** Each `<host>-homelab-worker` is an ordinary untagged member owned by the maintainer, enrolled by one interactive
  login that the maintainer approves once per worker. `tailscaled` keeps its state on the worker data disk, so a restart
  reconnects without another login. The image's unit was corrected to match in livespec-dev-tooling#3445.
- **ACL.** No change is needed. The flat grant already admits 6443, 10250 and UDP 8472 in both directions.
- **Auth key and 1Password item.** Neither is needed.
- **Still needed.** The Option A per-node `/32` subnet routes (005 §3) are node preferences on poweredge, gmktec and hp, plus a
  route approval in the admin console. They are not a policy edit. They are also host changes, so they go through each node's
  owner, and they come after the fixture proof below.

The ledger item livespec-dev-tooling-5pxg5r's Definition of Done was rewritten to match (CORRECTION comment on that item).

## 2. The egress-selector change waits for the fixture

`SPECIFICATION/non-functional-requirements.md`, "Homelab worker nodes", "Reviewed cluster changes": every production
control-plane or network change a worker needs MUST be proved against an isolated K3s fixture matching the fleet's version and
network configuration **before** it is applied to the production fleet.

livespec-dev-tooling#3430 merged `egress-selector-mode: "disabled"` into `ci-runner/k3s/phase2/k3s-config/config.yaml` before
any fixture proof existed. Merging alone does not apply it. The key takes effect only when the k3s server restarts, and on
2026-11-04 at 23:59Z poweredge's k3s had been running since 2026-11-02 09:42 PST. The coordinator was asked to keep the k3s server
restart out of the combined petri window, and to report whether the `k3s_config` role has already written the key into the live
`config.yaml`. If it has, any restart or reboot would apply it, and the key is commented out again until the fixture proof is
posted on livespec-dev-tooling-y4unt4 (hold recorded on that item, 23:59Z).

## 3. First fixture: k3d inside the M4 Max worker VM

005 §3 already names the cheaper first step: k3d alone on the worker VM's network. That step is now the first fixture, because
it proves every gate that does not need the tailnet:

- **Where.** Inside `macbook-m4-max-homelab-worker`. The VM already runs Docker, has 12 CPUs and 64 GiB, and passed the
  capability probe (macbook-m4-max-info `ac1617c`). No new VM and no tailnet device are needed. Creating containers in that VM is
  a host change, so the M4 Max info-repo agent runs the fixture scripts and records the run.
- **What.** k3d with `rancher/k3s:v1.36.2-k3s1`, one server and one agent, using the production server flags
  (`--disable traefik --disable servicelb`, `disable: [local-storage]`, `kubelet-arg max-pods=200`, vxlan flannel,
  10.42/16 and 10.43/16). The worker container (the real image, pinned by digest) is attached to k3d's Docker network as a
  generic kubelet with no K3s agent, which is exactly the shape that trips the `agent`-mode tunnel lookup.
- **Proves.** In `agent` mode, `kubectl logs` and `exec` against the worker fail with "failed to find Session" (the negative
  control). After a fixture server restart in `disabled` mode, logs, exec, port-forward and kubelet stats work on the worker,
  and logs still work on the k3d agent (the regression check). It also proves TLS bootstrap as `system:node:<name>`, the
  serving-CSR approver, the hold taint, pod-to-pod both ways, ClusterIP, DNS `10.43.0.10` and a NetworkPolicy deny.
- **Deferred to stage two.** The tailnet underlay split (a worker that cannot reach the fixture LAN directly, plus `/32` routes).
  Stage two needs a second untagged device approval and runs after stage one passes.
- **Teardown.** k3d's cluster and the fixture containers are removed after the proof. The worker VM and its data disk stay.

The fixture scripts are portable code under `homelab-worker/fixture/`, and their proof is host-captured on y4unt4.

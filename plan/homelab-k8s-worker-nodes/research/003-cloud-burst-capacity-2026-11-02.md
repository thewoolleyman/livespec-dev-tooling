# Cloud burst capacity for the home CI cluster

Research date: 2026-11-02 UTC. Recommendation, not an infrastructure authorization.

Provenance: published as `docs/research/2026-11-02-homelab-burst-worker-node.md` and moved into plan `homelab-k8s-worker-nodes` on 2026-11-04 as BACKGROUND research. Its subject is provisioned cloud machines and their economics, a separate option from the portable worker this plan implements; it is not implementation authority for the plan. Its workload-admission, local-storage and throughput criteria still inform the portable worker; cloud deployment and autoscaling are explicit later scopes of [001-macbook-air-first-dogfood.md](001-macbook-air-first-dogfood.md).

## Decision

**Yes, a small cloud worker can relieve the home machines. The shortest path is a separately provisioned, disposable x86 Ubuntu/k3s CI worker, not an extension of an already running mi-homelab Talos cluster.** That successor cluster has no provisioned machines declared yet. The Hetzner track supplies useful credential plumbing but creates no Kubernetes capacity.

Start with a single manually enabled worker and one ARC canary workload. A Hetzner CX53 (16 shared vCPU, 32 GB) is an attractive conditional pilot: about **$13.70 for 240 billable hours or $35.59 for a continuously retained month**, including one IPv4 address, before tax. Its price and availability qualifications are below. A CX43 is cheaper for one factory sandbox; neither shared-CPU SKU promises sustained compiler performance. Do not build an autoscaler before proving that the worker improves completed jobs per hour and p95 queue-to-result time.

**AWS does not change this.** EKS cannot act as a worker-only node joined to an existing non-EKS cluster: every EKS node registers with an EKS control plane billed per cluster-hour. The AWS equivalent of this recommendation is a plain EC2 k3s agent. A comparable x86 instance in `us-east-1` costs about **$88 burst / $251 retained on Spot, or $181 / $533 on-demand**, roughly 6–15× the CX53 (see [AWS comparison](#aws-comparison-eks-and-ec2)).

**Expected relief is modest per node.** Measured against poweredge (72 Haswell threads, 377.8 GiB), one CX53 supplies about **11–24% of its CPU and 8.5% of its memory**, after adjusting for per-vCPU speed. A c7a.4xlarge supplies about 46% of its CPU. CPU, not memory, is the binding resource. See [expected load relief](#expected-load-relief-measured-against-poweredge).

This is a **3–5 engineer-day integration estimate**, not an install-command estimate. Production autoscaling adds work. It has bounded migration rework: retain IaC, scoped identity, workload policy and telemetry, but replace Ubuntu/k3s bootstrap with Talos/Omni/KubeSpan when the successor substrate is ready. A worker attached to the home API server is burst capacity, **not independent backup during a home outage**.

## Evidence and limits

Repository sources were read at these revisions:

| Repository | Revision | Evidence |
|---|---|---|
| livespec-dev-tooling | `6c3b6c7c5180bc435c795cec1d4d30189ba2b8c3` | CI manifests, Ansible host variables, capacity/storage guidance and owning plans |
| mi-homelab/homelab | `e47a81b4e049b5f403b8e5c886b36e34e83093b3` | Current specification, infrastructure roots, execution receipts and plans |
| hetzner-xubuntu-info | `73bdcff6e89b4b015a3bdf15ce6fe7b462b2ebbf` | Current specification and bootstrap/adopter research |

Read-only Kubernetes observations at approximately **19:50–19:51Z** confirmed three Ready Ubuntu nodes, all on `v1.36.2+k3s1`, with LAN InternalIPs. Allocatable CPU was poweredge 72, gmktec 32, hp 14.5; advertised churn slots were respectively 32, 12 and 0. Factory quota usage was 13 pods / 52 CPU / 99,190 MiB requested, against 64 CPU and 128 GiB request limits. The Pending-phase list included 16 ARC pods, a gate pod and three storage helpers; ARC entries included scheduling-gated and container-creating states. Recent FailedScheduling events explicitly named insufficient `ci-runner.io/churn-slot` and an untolerated taint. This is a sample, not an average.

The assignment's earlier ~19:40Z observations—36 Pending ARC runners; gmktec 0–2% idle, poweredge ~1% idle, hp 25–50% idle; factory p50 2.3 cores and peak-memory p90 ~6.4 GiB—are supplied measurements, not independently remeasured percentiles. They support investigating overflow, not a new concurrency cap. Throughput, job mix, p95 duration and API responsiveness must determine that cap, as required by [capacity guidance](../../../.ai/ci-node-capacity-reads.md).

No cloud resources, host configuration or secrets were changed. No invoice/CUR/Cost Explorer audit or all-region cloud inventory was performed. The **$2,000+/month total is the maintainer's estimate**, not verified spend. Home geography, home-to-candidate RTT, direct-versus-relayed VPN paths and provider stock remain unmeasured; the session timezone is not evidence of home location.

## What mi-homelab and the Hetzner track actually provide

The [current homelab specification](https://github.com/mi-homelab/homelab/blob/e47a81b4e049b5f403b8e5c886b36e34e83093b3/SPECIFICATION/spec.md) defines a Git-governed Talos fleet: AWS control plane and infrastructure workers in `us-east-1`, Hosted Omni for machine lifecycle, Flux for workloads, KubeSpan for encrypted node transport, and Tailscale for administrative access. The pilot is one control-plane machine plus one infrastructure worker; the intended later shape is three plus two across availability zones. These are intended roles, not running instances. The Hosts section is empty apart from an example template. There are no committed operational Omni machine/cluster declarations or Flux bootstrap sources/syncs; one cluster policy manifest exists.

There **is real AWS infrastructure**. The [execution record](https://github.com/mi-homelab/homelab/blob/e47a81b4e049b5f403b8e5c886b36e34e83093b3/execution-record.md) records nine KMS/S3 backend resources bootstrapped in the workload account in `us-east-1`, completed readback/receipt at 04:14:42Z, and a noncurrent populated-state restore at 06:44Z. An older deployment-layer note saying the backend does not exist is stale. This backend is not evidence that the shared credential service or cluster is deployed, and an empty managed-host inventory does not mean zero AWS expenditure.

The separate `homelab-gitops` AWS account is observed ACTIVE. Homelab owns its shared IAM, KMS and canonical parameter declarations; shared credential sources use `us-west-2` under a named exception to the fleet region. The prepared OpenTofu roots `infra/shared-credentials/` and `infra/owner-deployment/` provide per-client revocable bootstrap identity, temporary scoped reader credentials and exact SSM/KMS source grants. External consumers retain their existing owners and do not thereby join Talos/Omni/Flux. The [owner-deploy workflow template](https://github.com/mi-homelab/homelab/blob/e47a81b4e049b5f403b8e5c886b36e34e83093b3/infra/owner-deployment/workflow-template/WIRING.md) is explicitly inactive pending real identity, protected workflow and deployment proofs.

The Hetzner plan consumes this service for an interactive Xubuntu replacement for the development VPS. Its [published-source profile](https://github.com/thewoolleyman/hetzner-xubuntu-info/blob/73bdcff6e89b4b015a3bdf15ce6fe7b462b2ebbf/plan/bootstrap-credentials-and-onboarding/research/009-published-source-only-profile.md) is prepared, not installed runtime credentials. The owner ledger read through 19:29Z still held provisioning behind a source KMS-policy Resource repair and subsequent client/tooling dependencies; the adopter anchor remained `unassigned`.

The recorded Hetzner machine is **Server Auction, FSN1-DC16**, with authenticated provider `ready` evidence. Hardware, usable recovery path and current OS/disk state are not established by that response. Most importantly, the [ratified Hetzner specification](https://github.com/thewoolleyman/hetzner-xubuntu-info/blob/73bdcff6e89b4b015a3bdf15ce6fe7b462b2ebbf/SPECIFICATION/spec.md) explicitly forbids enrolling that host as Kubernetes capacity. Its former worker reservation was superseded. A **new Cloud VM** is the candidate here; spare capacity on that auction server is not assumed available. Existing access proves Robot authentication for the dedicated server, not a Hetzner Cloud project, API credential or provisioning grant. Establishing Cloud ownership and scoped credential issuance is a new pilot prerequisite.

## What has to move with a workload

| Workload | Current binding constraint | What a cloud worker needs |
|---|---|---|
| ARC CI | Kueue admission plus per-node `ci-runner.io/churn-slot`; runner/workflow pod pair and local PVC | A measured node slot advertisement and queue allocation, compatible OS/kernel, pinned container hook, AppArmor profile, user namespaces, local storage and paired-pod placement |
| Delegated gate Jobs | `gates-flavor` selects gmktec's hostname; 15 CPU / 24 GiB queue; source mirror lives on poweredge | An additional reviewed flavor/quota and target routing; source/ref integrity preserved; remote mirror, credentials and local ephemeral PVC support |
| Factory sandboxes | Fixed 4 CPU / 7630 MiB requests and limits; factory-node selection, namespace quota and dispatcher limits | Node eligibility and placement, image pull and credential projection, API/exec reachability, telemetry and service egress; fleet limits only revisited from measured throughput |

Sources: [ARC values](../../../ci-runner/k3s/phase2/arc/values-livespec-dev-tooling.yaml), [hook template](../../../ci-runner/k3s/phase2/arc/hook-pod-template.yaml), [gates queue](../../../ci-runner/k3s/phase2/kueue/cluster-queue-gates.yaml), [gate template](../../../ci-runner/k3s/phase2/gates/gate-job-template.yaml), [factory namespace](../../../ci-runner/k3s/phase2/factory/factory-namespace.yaml), and [gmktec inventory](../../../ansible/inventory/host_vars/gmktec-xubuntu.yml). Historical quota derivations contain superseded snapshots; current YAML and live readback govern the numbers above. Factory admission is not Kueue admission. `factory-mi-homelab` is also a distinct namespace/credential boundary, not interchangeable with `factory`.

Factory sizing must use requests, not 2.3-core median usage. With positive system-pod requests, an 8-vCPU node generally fits only **one** 4-CPU sandbox; two consume all nominal CPU before the system. On a 16-GB machine memory is also too tight to promise two. A 16-vCPU/32-GB CX53 has room for **at most three** such sandboxes after overhead, before any ARC/gate sharing. These are conservative packing estimates, not measured throughput or authorized caps. Do not shrink reservations on the strength of a p90 or median. ARM CAX/t4g prices are not substitutes until all images, toolchains and checks are proven multiarchitecture.

The [local-path provisioner](../../../ci-runner/k3s/phase2/local-path-provisioner/local-path-provisioner.yaml) binds storage to the selected node and seeds caches using same-filesystem reflinks. The home layout separates cache, containerd and work-volume tiers; a VM can initially use one appropriately formatted local disk with separate directories and space monitoring, rather than reproduce the physical LVM layout. Preserve XFS/reflink expectations if using the existing seed path. A PVC does not migrate to another node on deletion. Never stretch home disks, NFS workspaces or synchronous replicated storage across the WAN.

Warm container images and dependency caches are valuable only if retained long enough to amortize their fetch. Pull immutable images directly from their registry; prewarm a rebuilt worker before admitting jobs. Compare cold and warm timings. Home Redis/crates-proxy and gate mirror traffic can erase CPU gains through latency or home uplink load; use node/cloud-local reconstructible caches or an explicitly tested cold path. A persistent cache volume adds storage cost even when compute is absent. See [storage guidance](../../../.ai/ci-node-storage-tiers.md).

## Options, work and ownership

Estimates are engineering effort for one person familiar with this fleet, including ordinary review and failure-path testing; they exclude waiting for credentials, stock or owner approvals. No option has been deployed or benchmarked by this research.

### A. One cloud k3s agent attached to the home cluster — smallest pilot

**3–5 days:** provisioning/identity 0.5–1; network validation and configuration 1–2; runner/storage integration 0.5–1; cold/warm, drain/recreate and mixed-load proof 1. A subsequent automatic create/delete controller adds roughly 2–4 days.

Use a new x86 VM, pinned k3s version, dedicated identity, explicit cloud-worker label and initial taint. Install only the CI node dependencies, then expose it to one canary scale set. Tailscale reachability to `poweredge:6443` alone is insufficient: today's nodes advertise LAN addresses and use Flannel. Choose and prove a bidirectional underlay for all node endpoints—carefully scoped subnet routing preserving the existing LAN underlay, or a reviewed change to the node/Flannel address plane. Do not switch every live node's transport merely to make a one-node trial easy.

Prove cross-node pod traffic, DNS/Services, kubelet/log/exec paths, NetworkPolicy, MTU and reconnect behavior. Keep API, kubelet and VXLAN private; never expose UDP 8472 publicly. The upstream [K3s multicloud guide](https://docs.k3s.io/networking/distributed-multicloud) warns about latency and labels its built-in Tailscale integration experimental. Its all-node VPN configuration is not a drop-in addition to this existing cluster. [K3s networking requirements](https://docs.k3s.io/installation/requirements) specify the peer ports. Measure candidate-to-poweredge latency and useful transfer rate; no RTT is inferred here.

The cloud node joins the home cluster's trust domain. Use an agent-specific join credential, scoped enrollment identity and narrow ACLs; keep credentials out of images, snapshots, Terraform state and cloud-init logs. Revoke node/bootstrap identity on deletion. Do not give build pods cloud account or tailnet administration credentials. Preserve existing workload sandboxing and metadata-service restrictions.

This option best fits disposable ARC jobs first. Gates need the flavor/source-path work above. Factory work follows only after network and persistence behavior are proven; interrupted multi-hour model runs may cost more than the VM saved. Home power, internet and the poweredge API remain dependencies.

Owner: **livespec-dev-tooling** for CI provisioning/manifests; **tailscale-admin** for enrollment and routing/ACL policy; **homelab shared-gitops-credential-bootstrap** only for reusable scoped sources where needed. Do not fold worker implementation into the interactive Hetzner onboarding plan. Factory integration coordinates with **gmktec-factory-placement**, the orchestrator's **kubernetes-sandbox-backend**, and the current dispatcher owner.

### B. Autoscaled home-cluster cloud pool — after A proves value

**5–9 days total for a small bespoke queue-aware controller**, or **7–12 days for Cluster Autoscaler integration**, including A. Implement a bounded desired-node count, independent controller, idempotent create/join, readiness/warming, admission integration, cordon/drain, credential cleanup, deletion and a cost ceiling. Observe queue age and blocked-resource reasons, not generic Pending count or host load average.

The upstream [Hetzner Cluster Autoscaler provider](https://github.com/kubernetes/autoscaler/blob/master/cluster-autoscaler/cloudprovider/hetzner/README.md) supports pool configuration, image/cloud-init and scheduling labels/taints. It is not an AWS-style native managed autoscaling group. Verify the chosen version's scale-from-zero node template, including this fleet's custom churn resource. Kueue-suspended/gated workloads may never become the unschedulable pods that trigger a normal autoscaler; fixed queue quotas can hide demand. Do not assume installing the controller makes ARC burst automatically.

On Hetzner, **delete** to stop compute charges; power-off is still billed. Retain no secrets in reusable images. Local PVCs, daemon workloads and running jobs complicate scale-down; never force drain factory/gate work to meet a timer. An external/manual wake mechanism is necessary if the whole execution cluster is scaled to zero. Keep provider writes under one owner; Terraform and an autoscaler must not fight over the same VM lifecycle.

An AWS ASG or Cluster Autoscaler is technically an alternative, but it is outside current homelab policy. A separately governed CI extension still needs explicit account/IAM/cost ownership; it is not permission to evade the homelab policy checker. Ownership otherwise matches A, with homelab review for any policy change.

### C. AWS Spot burst workers — cheap compute, expensive interruptions

**8–14 days total** for a defensible pool: A/B integration plus diversified instance/AZ capacity, interruption detection, draining, on-demand fallback, durable result delivery and explicit lost-run accounting. Networking and home dependencies remain as in A if workers join k3s. Use least-privilege instance identity, block workload access to management credentials, and keep cache storage costs explicit.

[AWS interruption notices](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/spot-instance-termination-notices.html) are best effort, normally two minutes before stop/termination. Suitable first for disposable CI work with explicit restart semantics. A lost gate has no verdict; a new invocation is a new measurement, not a masked retry. Long factory runs need verified recovery before Spot is useful. Current Spot quotes, taken 2026-11-03, are in the [AWS comparison](#aws-comparison-eks-and-ec2); they are point-in-time prices, not a fixed discount. Do not assume Hetzner has an equivalent Spot product.

### D. Separate cloud execution cluster — better isolation, more integration

**5–8 days for a minimal k3s proof, 8–15 for an operable service**. A Talos-first proof from today's state is a lower-confidence **10–20+ day estimate**, because it includes unfinished owner deployment, pilot control plane, Omni/Flux bootstrap and network proofs rather than merely changing an image; this is not an estimate for the whole home migration. A single combined server/worker is a cheap non-HA proof; separate control-plane and worker capacity raises the persistent bill. An always-on small controller can wake workers from zero, while a fully deleted cluster needs an external wake/bootstrap path.

Run ARC against a distinct scale set and deliberately route a selected repository via its runner variable; do not assume two clusters automatically share a queue or provide federation. GitHub documents [multiple-scale-set availability patterns](https://docs.github.com/en/actions/how-tos/manage-runners/use-actions-runner-controller/deploy-runner-scale-sets), but routing and failure behavior need a fleet-specific proof. Configure Fabro with a distinct target/namespace/credential and prove that the serving backend can select it; its current configuration is not evidence of transparent multicluster dispatch. Gates additionally need an independent source mirror and the same tree/base-ref checks.

Keep pod/Service CIDRs nonoverlapping wherever routed. Cluster-local storage/cache avoids the WAN dataplane and separates cloud-worker trust from the home cluster. Administrative access can remain on Tailscale. It becomes meaningful home-outage backup only after API/controllers, source delivery, credential issuance, telemetry and any required Fabro service also survive that outage. A cloud cluster whose dispatcher or mirror remains at home is only partially independent.

Owner: CI services remain with livespec-dev-tooling and the factory backend owner; a Talos fleet belongs to **homelab/fleet-substrate-boot-identity-and-network**, with guardrails and identity from the existing homelab plans. This is the durable direction if independent backup is a requirement now; it is more work than overflow alone.

## Cost and comparison with current spending

All calculations are estimates, before tax, with no commitments or discounts. Burst means **8 billable hours/day × 30 = 240 hours**; continuous AWS means **730 hours**. Cold start, image warming and drain time are billable too. Hetzner hourly use is rounded up; its monthly cap applies per retained server, so repeatedly replacing many short-lived servers does not promise the same aggregate cap. USD list prices below are provider USD prices, not an assumed EUR exchange rate.

| Candidate | List compute price | 240 h compute | Continuous compute | Evidence as accessed 2026-11-02 |
|---|---:|---:|---:|---|
| Hetzner CX43, EU, 8 shared vCPU / 16 GB / 160 GB disk | $0.0296/h (€0.0256) | $7.10 | $18.49 cap (€15.99) | Live provider feed, product `CLOUD_134` |
| Hetzner CX53, EU, 16 shared vCPU / 32 GB / 320 GB disk | $0.0561/h (€0.0473) | $13.46 | $34.99 cap (€29.49) | Live provider feed, product `CLOUD_135` |
| Hetzner CCX33, NBG1/HEL1, 8 dedicated vCPU / 32 GB / 240 GB disk | $0.2612/h (€0.2219) | $62.69 | $162.99 cap (€138.49) | Live provider JSON price feed |
| AWS m7i.2xlarge, us-east-1, Linux shared tenancy, 8 vCPU / 32 GiB | $0.4032/h | $96.77 | $294.34 | Live AWS price feed and offer CSV; effective 2026-10-01 |
| Same AWS size, hypothetical Spot at 50–70% below on-demand | **Estimate:** $0.1210–0.2016/h | $29.03–48.38 | $88.30–147.17 | Sensitivity only; not a current Spot offer |

Price sources: [live Hetzner product-price feed](https://www.hetzner.com/_resources/app/data/app/live_data_prices.json), [live CCX provider feed](https://www.hetzner.com/_resources/app/data/bench/cloud_data.json), [AWS us-east-1 offer CSV](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/current/us-east-1/index.csv). AWS SKU `99TZRNZAZSFRSS24` identifies the quoted Linux m7i.2xlarge rate. The CX feed lists NBG1/FSN1/HEL1 at the quoted rates; product `CLOUD_21` supplies the IPv4 addon. The [CX product page](https://www.hetzner.com/cloud/cost-optimized/) also confirms the sizes and EUR prices including IPv4, but displays “not available”; the [CCX page](https://www.hetzner.com/cloud/general-purpose/) likewise does not prove stock. A product-price record marked active is not a capacity reservation. Reconfirm actual location, availability and price before purchase.

Additional costs, also checked 2026-11-02:

- [Hetzner Primary IPv4](https://docs.hetzner.com/cloud/servers/primary-ips/overview/): $0.001/h, $0.60/month cap (€0.0008/h, €0.50/month). IPv6 is free, but IPv6-only bootstrap is not presumed compatible. A retained IPv4 costs money even between deleted workers. [Billing rules](https://docs.hetzner.com/cloud/billing/faq/) bill servers until deletion. Included local disk is already in the table; snapshots/extra persistent volumes are additional and not quoted here.
- [AWS IPv4](https://aws.amazon.com/vpc/pricing/): $0.005/h, or $1.20/240 h and $3.65/730 h; retained idle addresses are also charged. For planning, 100 GB gp3 retained all month is **$8/month**, using the $0.08/GB-month example on [EBS pricing](https://aws.amazon.com/ebs/pricing/); this is a storage-budget assumption, not an authenticated account quote. Extra IOPS, throughput, snapshots and egress add to it.
- Thus one m7i.2xlarge plus that retained disk and active-only IPv4 is approximately **$105.97 burst / $305.99 continuous** before egress. The Spot sensitivity becomes **$38.23–57.58 / $99.95–158.82**. AWS networking can materially change this: its pricing example charges $0.045/NAT-hour plus $0.045/GB processed, and internet transfer can be $0.09/GB after applicable allowances. A NAT gateway is also forbidden by current homelab policy; none is included in these totals.
- Hetzner CX53 plus active-only IPv4 gives **$13.70 burst / $35.59 retained**, or about **0.7% / 1.8%** of $2,000. CCX33 plus IPv4 gives **$62.93 / $163.59**, about **3.1% / 8.2%**. AWS on-demand totals are about **5.3% / 15.3%**. Four retained CX53s would be $142.36/month before tax; four AWS examples $1,223.96. These arithmetic scenarios do not imply either fleet has validated workload capacity.
- [Current Omni pricing](https://www.siderolabs.com/pricing) and [signup](https://www.siderolabs.com/omni-signup) now list Hobby as **free, up to ten nodes/two users**. Cached older $10 references should not be used as current list price. Existing account terms were not inspected. Crossing the ten-node boundary needs review; current Startup list price is $25/node/month, not simply a $25 eleventh-node surcharge assumption.
- For option D, a separate small control-plane/controller VM remains billable even when workers are absent. A CX23 (2 vCPU/4 GB), listed in the same live feed as `CLOUD_132` at $0.0104/h or $6.49/month, adds **$7.09/month including IPv4** if retained. With a CX53 worker this gives an indicative **$20.79 burst / $42.68 continuous** cluster floor before other services, subject to stock and validation of control-plane capacity. This two-node shape is not HA. Tailscale account/device entitlements and incremental observability charges were not audited and are excluded.

For a single CX53, daily delete/recreate saves roughly **$21.89/month** against retaining it. Several days of autoscaler engineering solely to save that amount are hard to justify. Retaining one worker may be the lower total-cost pilot; deletion becomes valuable for rare use or a larger pool. Conversely, dedicated CPU is substantially dearer than the cheapest shared SKU, so benchmark useful builds per dollar rather than vCPU count.

This spends more money to buy throughput and reduce home contention. It does not inherently reduce Anthropic/OpenAI token use, Honeycomb charges, Contabo or existing AWS bills. Faster dispatch may **increase** model spend. No savings ranking against those services is defensible without their measured usage/billing; no token-savings claim is made here. Home electricity savings are also unpriced without watts and tariff measurements.

## AWS comparison (EKS and EC2)

Added 2026-11-03 at the maintainer's request. All AWS prices below were read live on 2026-11-03 for **`us-east-1`** (US East, N. Virginia). That region is chosen because the mi-homelab AWS backend and planned control plane already live there, and because the m7i.2xlarge row in the cost table above uses it. Home-to-region latency is still unmeasured. Frankfurt (`eu-central-1`) on-demand rates for the same instances are 14–20% higher.

### Can EKS be only a worker node in an existing cluster?

**No.** EKS has no worker-only product that joins a cluster it does not manage. The [EKS pricing page](https://aws.amazon.com/eks/pricing/) states: "All Amazon EKS clusters have a per cluster per hour fee", and every EKS node type registers with the control plane of an EKS cluster. That covers EC2 node groups, Fargate, Auto Mode and Hybrid Nodes. [EKS Hybrid Nodes](https://docs.aws.amazon.com/eks/latest/userguide/hybrid-nodes-overview.html) is the reverse direction: "you can use your on-premises and edge infrastructure as nodes in Amazon EKS clusters", and "AWS manages the AWS-hosted Kubernetes control plane". The home machines would join an AWS control plane, not the other way round. [EKS Anywhere](https://aws.amazon.com/eks/eks-anywhere/) is a separate product that creates and operates whole clusters on your own infrastructure. It does not add a node to an existing k3s cluster either.

The same answer holds for the later Talos cluster. Its worker on AWS would be an EC2 instance running Talos and enrolled through Omni, as the homelab specification already plans. That is still not EKS.

The real AWS equivalent of this report's recommendation is therefore **a plain EC2 instance running a k3s agent**, joined to the existing cluster exactly like the Hetzner CX53. It has no EKS and no control-plane fee.

### EC2 worker prices next to the Hetzner pilot

Scenarios match the cost section: **240 h** burst and **730 h** retained. Every AWS total adds a public IPv4 address at $0.005/h ($1.20 / $3.65) and a 100 GB gp3 root volume retained all month at $0.08/GB-month ($8.00), the same assumptions as the m7i row above. A 320 GB gp3 volume, matching the CX53's included disk, would cost $25.60/month instead of $8.00. Egress is excluded from the totals and treated below.

| Candidate, `us-east-1` unless noted | vCPU / RAM | On-demand $/h | Spot $/h (Spot discount) | Spot interruption band | 240 h total, on-demand / Spot | Retained total, on-demand / Spot |
|---|---|---:|---:|---|---:|---:|
| **Hetzner CX53** (EU, shared vCPU, 320 GB disk, IPv4) | 16 / 32 GB | $0.0561 | n/a | n/a | **$13.70** | **$35.59** |
| Hetzner CCX33 (EU, dedicated vCPU, IPv4) | 8 / 32 GB | $0.2612 | n/a | n/a | $62.93 | $163.59 |
| c7i.4xlarge (Intel, x86) | 16 / 32 GiB | $0.7140 | $0.3279 (54%) | >20% | $180.56 / **$87.90** | $532.87 / **$251.02** |
| c7a.4xlarge (AMD, x86) | 16 / 32 GiB | $0.8211 | $0.3811 (54%) | 5–10% | $206.27 / $100.66 | $611.07 / $289.85 |
| c7g.4xlarge (Graviton3, arm64) | 16 / 32 GiB | $0.5800 | $0.2531 (56%) | <5% | $148.40 / $69.94 | $435.05 / $196.41 |
| m7a.2xlarge (AMD, x86) | 8 / 32 GiB | $0.4637 | $0.2065 (55%) | >20% | $120.48 / $58.76 | $350.14 / $162.40 |
| m7i.2xlarge (Intel, x86; the cost table's example) | 8 / 32 GiB | $0.4032 | $0.1774 (56%) | >20% | $105.97 / $51.78 | $305.99 / $141.15 |

Sources, read 2026-11-03:

- On-demand Linux rates come from the AWS pricing-page data feed for [US East (N. Virginia) Linux](https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/ec2/USD/current/ec2-ondemand-without-sec-sel/US%20East%20(N.%20Virginia)/Linux/index.json), published 2026-10-29. The m7i.2xlarge rate code `99TZRNZAZSFRSS24` matches the SKU already quoted above.
- Spot rates come from the feed behind the [EC2 Spot pricing page](https://aws.amazon.com/ec2/spot/pricing/) (`website.spot.ec2.aws.a2z.com/spot.js`). Interruption bands come from the [Spot Instance Advisor](https://aws.amazon.com/ec2/spot/instance-advisor/) data (`spot-bid-advisor.s3.amazonaws.com/spot-advisor-data.json`). Spot prices move, and AZ choice changes both price and interruption rate.
- IPv4 comes from [VPC pricing](https://aws.amazon.com/vpc/pricing/), where in-use and idle addresses are both $0.005/h. gp3 storage comes from the [EBS pricing](https://aws.amazon.com/ebs/pricing/) feed: $0.08/GB-month, 3,000 IOPS and 125 MB/s included.

Egress is the cost Hetzner mostly does not have. Inbound transfer, such as image and dependency pulls into EC2, is free. Traffic **out** of EC2 to the internet is billed at $0.09/GB for the first 10 TB/month after a 100 GB monthly free allowance, per the [EC2 on-demand pricing page](https://aws.amazon.com/ec2/pricing/on-demand/). That allowance is shared across the whole account and all regions. Outbound traffic here includes kubelet and API traffic, logs, results, and any writes to home caches such as Redis or sccache, all carried over the tailnet. 200 GB/month beyond the allowance would add $18. Measure this in the pilot rather than assuming it.

**Reading the table.** The cheapest **x86** 16-vCPU option, c7i.4xlarge on Spot, is about **6.4× the CX53 for burst and 7.1× retained**. On-demand it is **13–15×**. Graviton is cheaper and interrupts least, but the report already excludes arm64 until every image, toolchain and check is proven multiarchitecture. The comparison flatters Hetzner on one axis: CX53 vCPUs are shared, while c7i/c7a vCPUs are full, non-burstable vCPUs. The like-for-like dedicated comparison is the CCX33. Even so, an 8-vCPU m7i.2xlarge on Spot ($51.78 / $141.15) is in the same range as a CCX33 ($62.93 / $163.59), but it carries an interruption risk the CCX33 does not. **The numbers do not warrant changing the recommendation.** AWS is the fallback if Hetzner stock or sustained-CPU benchmarks fail. Even then, the next candidate is the CCX33 before AWS, unless the benchmark shows that AWS Spot gives more useful builds per dollar.

### EKS proper, for completeness

The cluster fee from the [EKS pricing page](https://aws.amazon.com/eks/pricing/) is **$0.10 per cluster-hour on standard support ($73.00/month)**, or **$0.60 per cluster-hour on extended support ($438.00/month)**. The control plane bills for every hour the cluster exists, even when no worker is running. A new EKS cluster plus one on-demand c7i.4xlarge node therefore costs about **$253.56 burst / $605.87 retained** on standard support, or **$618.56 / $970.87** on extended support. With a Spot node it costs $160.90 / $324.02 on standard support. These totals exclude Auto Mode, Provisioned Control Plane and any NAT gateway.

[EKS Hybrid Nodes](https://aws.amazon.com/eks/pricing/) charges **$0.020 per vCPU-hour** for the first 576,000 vCPU-hours a month, on top of the cluster fee. Moving the home machines under an EKS control plane, about 118.5 allocatable vCPU, would cost roughly **$1,730/month plus $73**. Billing counts the vCPUs reported to Kubernetes, so the real figure is likely higher. AWS also asks for an account-team conversation for machines above 32 vCPU, which poweredge (72) is.

**Why EKS does not fit.** EKS gives a *new* cluster with its own control plane, not a worker for the existing one. Using it means running a second cluster, which is option D with a $73/month control-plane floor that AWS manages, rather than Hetzner's $7.09 CX23. Alternatively it means migrating the home cluster under AWS's control plane through Hybrid Nodes. The homelab constraints also forbid managed Kubernetes control-plane fees (see the table below).

### Integration differences from the Hetzner pilot

- **Networking.** Tailscale on EC2 behaves as it does on Hetzner. The same unsolved underlay problem from option A applies, because the cloud node must reach LAN node addresses and Flannel. On AWS the instance needs a public subnet and public IPv4 for a direct WireGuard path, or it falls back to DERP relays. A NAT gateway costs $0.045/h plus $0.045/GB and is forbidden by homelab policy. The security group can stay closed inbound. Traffic leaving the tailnet toward home is billable egress, whereas Hetzner includes traffic. The latency from `us-east-1` to home is unmeasured, like the Hetzner path.
- **Spot interruptions.** The notice is a best-effort two minutes. The worker needs an interruption watcher, such as aws-node-termination-handler or an IMDS poller, to taint, cordon and drain. A killed ARC job fails its GitHub check and needs an explicit re-run, never a masked retry. Gates and factory runs stay off Spot, as option C already says. Prefer the instance types with low interruption bands and diversify across AZs. In `us-east-1` today, c7i.4xlarge sits in the >20% band and c7a.4xlarge in the 5–10% band.
- **Governance.** The homelab AWS allowlist permits only t4g.small/medium and gp3 volumes up to 20 GiB, and denies ASGs. Any of these instances therefore needs a separately owned account, or an explicit policy decision. It is not a quiet use of the homelab account.
- **Effort.** An on-demand EC2 worker keeps option A's **3–5 days**. Add about 0.5–1 day for the VPC, security group, instance profile and account or cost ownership, which Hetzner does not need beyond its Cloud project. Spot moves the estimate to option C's **8–14 days**. An EKS-based route is option D's 5–8 / 8–15 days plus EKS-specific IAM, VPC CNI and add-on work. Hybrid Nodes is a cluster migration, not a burst pilot.

## Expected load relief, measured against poweredge

Added at the maintainer's request: how much of poweredge's work each option could plausibly take, as a percentage of poweredge's CPU and memory.

**The baseline, read live at about 23:50Z on 2026-11-02**, via `lscpu`, `free` and `k3s kubectl` on the host: poweredge is a dual **Xeon E5-2696 v3** (Haswell, 2014). It has 2 × 18 cores, which gives **72 hardware threads**. It also has **377.8 GiB** RAM, with 72 CPU and 377.8 GiB allocatable, and it advertises **32 churn slots**. At that moment its pods requested 29.25 CPU (40%) and 55.7 GiB memory (14%), and the 1-minute load average was **229 on 72 threads**. **CPU is the binding resource. Memory is not.** poweredge uses about a seventh of its RAM by request. The memory percentages below are therefore small but rarely the limit, and the CPU column is the one that predicts relief.

**Per-vCPU speed.** A vCPU count alone misleads, because a cloud vCPU and a poweredge thread do different amounts of work. The adjustment uses [PassMark](https://www.cpubenchmark.net/) multithread ratings divided by thread count, read 2026-11-03:

| CPU | Multithread rating | Ratings per thread | Relative to poweredge |
|---|---:|---:|---:|
| E5-2696 v3 (18 cores / 36 threads; poweredge) | 21,144 | 587 per thread | 1.00 |
| Xeon Platinum 8488C (48 cores / 96 threads; c7i, m7i) | 88,667 | 924 per thread | **1.57** per vCPU, where each vCPU is a hyperthread |
| EPYC 9R14 (96 cores / 192 threads; c7a, m7a) | 116,475 | 1,213 per core | **2.07** per vCPU. On 7th-generation AMD instances each vCPU is a full physical core |
| EPYC 7763 (Milan, 64 cores / 128 threads) / EPYC 9R14 per thread | 84,004 / 116,475 | 656 / 607 per thread | **1.03–1.12**, used for a dedicated AMD hyperthread such as Hetzner CCX. Hetzner says only "AMD", so the model is unconfirmed |
| Hetzner CX shared vCPU ("Intel/AMD", unspecified) | n/a | n/a | **0.5–1.1**, an assumption. Shared vCPUs carry no sustained-CPU promise, and contention lowers the floor |

Single-thread ratings favour the modern parts by less: 2,037 for poweredge against 3,113 for the 8488C and 2,518 for Milan. That matters for serial build steps. PassMark is a generic benchmark, not a compile benchmark. These factors are **planning estimates for the pilot to replace with measured jobs per hour**, not measurements of this fleet's workloads. c7g (Graviton) is shown at its nominal count only, because arm64 is excluded until proven.

| Option / candidate | vCPU / RAM | CPU vs poweredge, nominal count | CPU vs poweredge, speed-adjusted | Memory vs poweredge | Proportional share of poweredge's 32 churn slots | 4-CPU / 7.45 GiB factory sandboxes that fit |
|---|---|---:|---:|---:|---:|---:|
| poweredge (baseline) | 72 threads / 377.8 GiB | 100% | 100% | 100% | 32 | about 17 by CPU request |
| **A: Hetzner CX43** | 8 shared / 16 GB | 11% | 6–12% | 4% | 2–4 | 1 |
| **A: Hetzner CX53** (recommended pilot) | 16 shared / 32 GB | 22% | **11–24%** | 8.5% | 4–8 | at most 3 |
| A: Hetzner CCX33 | 8 dedicated / 32 GB | 11% | 11–12% | 8.5% | about 4 | 1 |
| A on AWS: m7i.2xlarge | 8 / 32 GiB | 11% | 17% | 8.5% | about 6 | 1 |
| A on AWS: m7a.2xlarge | 8 / 32 GiB | 11% | 23% | 8.5% | about 7 | 1 |
| A on AWS: c7i.4xlarge | 16 / 32 GiB | 22% | 35% | 8.5% | about 11 | at most 3 |
| A on AWS: c7a.4xlarge | 16 / 32 GiB | 22% | **46%** | 8.5% | about 15 | at most 3 |
| A on AWS: c7g.4xlarge (arm64) | 16 / 32 GiB | 22% | not estimated | 8.5% | n/a until multiarch | n/a |
| **B: pool of N workers** | N × the node | N × row | N × row; for example, 4 × CX53 = 44–98%, at $142/month retained | N × row | N × row | N × row |
| **C: Spot** | same rows as the AWS lines | same | same, **times the share of hours not lost to interruptions**, minus re-run work | same | same | none: factory and gates stay off Spot |
| **D: separate cluster** | workers as above, plus a control plane | same as the worker rows | same as the worker rows. The control-plane node (for example a CX23) adds **0%** | same | relief applies only to repositories routed to it | as worker |

How to read it:

- **The proportional churn-slot column is not a cap.** It is poweredge's 32 slots scaled by the speed-adjusted CPU share. It is a planning ratio, and the [capacity guidance](../../../.ai/ci-node-capacity-reads.md) forbids deriving a cap from vCPU counts. The pilot starts at one canary job and measures the real figure.
- **These are upper bounds.** Effective relief is lower by cold-cache and image-warm time, by WAN latency to home caches and the API server, and, on Spot, by lost and re-run jobs. A worker also only relieves what can be scheduled on it. Factory sandboxes need 4 CPU each, so a 16-vCPU node holds at most three.
- **Against the whole home cluster** the share is smaller. The three home nodes advertise 120 vCPU (72 + 32 + 16), and gmktec's Zen 5 threads are individually faster than poweredge's. A single CX53 is about 13% of that nominal count. A single c7a.4xlarge is the only one-node option that approaches half a poweredge.
- **Price per unit of relief.** On the speed-adjusted midpoint, a retained CX53 costs about **$2/month per poweredge-percent**: $35.59 for about 17.5%. A retained c7a.4xlarge on Spot costs about **$6.30**: $289.85 for 46%. On-demand it costs about **$13.30**: $611.07 for 46%. For burst use, a CX53 costs about $0.80 and a c7a on Spot about $2.20. This ranking holds unless the pilot measures the CX53's shared vCPUs near the bottom of their range, which is the case the CCX33 or c7a fallback exists for.

## Alignment with the Talos plan

The [binding constraints](https://github.com/mi-homelab/homelab/blob/e47a81b4e049b5f403b8e5c886b36e34e83093b3/SPECIFICATION/constraints.md) and [AWS cost checker](https://github.com/mi-homelab/homelab/blob/e47a81b4e049b5f403b8e5c886b36e34e83093b3/checks/aws-cost-policy.sh) make the boundary concrete:

| Existing decision | Consequence for this proposal |
|---|---|
| Managed Kubernetes machines run Talos, lifecycle through Omni | A temporary Ubuntu/k3s CI extension is outside that managed fleet; later drain/reimage/re-enroll, not an in-place agent conversion |
| KubeSpan node traffic; Tailscale administrative access only | The temporary Tailscale-dependent underlay must be replaced; it cannot satisfy the successor's access-plane outage independence |
| Provider-neutral `cloud` machine class | A future Hetzner Talos worker fits; provider stays metadata rather than a new architectural class |
| First provisioned host is an AWS control-plane node | A lone cloud worker does not complete the Talos pilot; bootstrap remains prerequisite |
| At most ten Omni-managed machines | Count burst machines too when enrolled; keep maximum desired size within the whole-fleet bound |
| No Kubernetes-driven AWS autoscaling, NAT Gateway or managed Kubernetes control-plane fees | ASG/CA-on-AWS or EKS requires a policy decision, not a hidden implementation change |
| Current AWS allowlist: t4g.small/t4g.medium, gp3 volumes ≤20 GiB; ASGs denied | The priced x86 AWS worker/100-GB disk is a comparison, not an allowed deployment under today's homelab declarations |
| No synchronous WAN distributed storage; caches reconstructible | Keep execution scratch local; move results to durable owned storage and test restore separately |
| Git-owned automation and distinct client ownership | One owner per resource, scoped service consumption, reviewed transfer when the worker becomes a Talos machine |

The historical rollout input explicitly includes [Phase 9: provider-neutral cloud worker](https://github.com/mi-homelab/homelab/blob/e47a81b4e049b5f403b8e5c886b36e34e83093b3/docs/talos-omni-architecture-and-rollout.md#phase-9--provider-neutral-cloud-worker), with placement/failover/network tests. This supports the direction; it is not implementation authority. Actual substrate belongs to `fleet-substrate-boot-identity-and-network`; cost/account identity belongs to `phase-1-cost-account-and-identity-guardrails`; reusable sources belong to `shared-gitops-credential-bootstrap`.

Reusable work: provider provisioning, ownership/cost tags, scoped source grants, container images, generic scheduling labels, cache policy and telemetry. Replaceable work: Ubuntu host setup, k3s join/bootstrap, Tailscale node transport and hostPath-specific runner plumbing. Talos' immutable/no-shell model means the current Ansible-installed hook and AppArmor paths need packaging or manifest changes; merely selecting a Talos image is insufficient. Once migrated, a low-cost cloud worker can remain burst capacity. True backup additionally requires the independent service paths described in option D.

## Smallest next step and acceptance criteria

The next implementation step is a **single-worker pilot design and canary**, owned by CI infrastructure, with explicit cloud-account, identity and network ownership. It should not wait for the whole Talos migration, and should not quietly reuse the interactive Hetzner machine. This report authorizes no provisioning.

1. Verify a purchasable x86 SKU/location and exact checkout price. Record candidate-to-home direct/relay path, latency, packet loss, MTU and transfer rate before enrolling a workload. If the existing underlay cannot support one remote worker without destabilizing home networking, choose the separate-cluster proof instead.
2. Provision one disposable worker through reviewed IaC/Ansible and scoped credentials; retain the initial taint until network, hook, storage and security checks pass. Start at one canary job, then measure increments rather than declaring a vCPU-derived slot cap.
3. Route one representative ARC workload, retaining the existing home route for rollback. Measure queue-to-start, completion throughput, p50/p95 duration, cold/warm image/cache time, home uplink, CPU accounting/steal, memory peaks, eviction/error rate and poweredge API latency. Include a heavy compile mix and record billed time per successful job.
4. Test graceful drain, VM deletion/recreation, stale node/identity cleanup and a lost-network case without killing existing production jobs. Every lost gate/run must be identifiable; no missing verdict may count as green. Do not put long factory runs on Spot during this proof.
5. Only after demonstrated net relief, integrate gates/factory and update their separate admission/placement policies. Decide whether to retain one cheap worker or implement bounded scale-to-zero. Record its Talos reimage/removal boundary and maximum spend before expanding.

The principal risks are WAN/control-plane dependence, queue rules hiding demand, cold-cache overhead, shared-CPU contention/stock scarcity, broadened cluster trust, interrupted expensive model work, and an unbounded node controller. The proposed proof directly tests each performance/lifecycle assumption before converting an inexpensive VM into a permanent operational obligation.

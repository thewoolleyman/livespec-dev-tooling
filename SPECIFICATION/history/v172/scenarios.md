# livespec-dev-tooling — scenarios

This file holds acceptance scenarios in Gherkin form. Each Gherkin keyword line is preceded and followed by a blank line so that every step renders as its own Markdown paragraph under GitHub-Flavored Markdown.

## Scenario: livespec consumes the package via uv git source

Given livespec's `pyproject.toml` declares `livespec-dev-tooling` under `[dependency-groups].dev` with `[tool.uv.sources]` pinning a `git = "https://github.com/thewoolleyman/livespec-dev-tooling.git"` and `tag = "vX.Y.Z"`

And livespec's `justfile` references each shared check as `uv run python -m livespec_dev_tooling.checks.<slug>`

When a contributor runs `just check` in the livespec repo

Then every check resolves to the package-provided module

And the run completes with exit code `0` on a clean working tree

## Scenario: every livespec-impl-* plugin consumes the package via `python -m`

Given a `livespec-impl-*` plugin's `pyproject.toml` declares `livespec-dev-tooling` under `[dependency-groups].dev` via `[tool.uv.sources]`

And the plugin's `justfile` invokes shared checks as `uv run python -m livespec_dev_tooling.checks.<slug>`

When a contributor runs `just check` in the plugin repo

Then each shared check runs against the plugin's working tree

And no plugin-local copy of any shared check is required

## Scenario: a CI workflow consumes the reusable check-matrix

Given a consumer's `.github/workflows/ci.yml` declares `jobs.check-suite.uses: thewoolleyman/livespec-dev-tooling/.github/workflows/reusable-check-matrix.yml@vX.Y.Z`

And the workflow input `checks` lists the slugs the consumer wants to run

When the workflow runs on `pull_request`, `push` to master, or `merge_group`

Then each matrix entry executes the named check via the `run-check` composite Action

And each merge-gating matrix entry executes on GitHub-hosted capacity without a self-hosted label from the shared factory host

And the matrix's pass/fail status is reported to GitHub as a required status check

Scenario: a codex-acp bump remains parked while the live receiver is disabled

Given a pin-freshness scan opens or finds a codex-acp bump PR

And the privileged host-only golden-master receiver workflow is administratively disabled

When the scan emits the `codex-acp-golden-master` repository dispatch

Then no component synthesizes a success callback or enables auto-merge

And the bump PR remains parked on the last verified version until an equivalent live proof succeeds

Scenario: a codex-acp package succession proves itself without the live receiver

Given the codex-acp pin's package is succeeded by a deliberate manual PR rather than a freshness-scan bump

And the privileged host-only golden-master receiver workflow is administratively disabled

When the cutover release is built

Then the predecessor package remains baked and unchanged on a transitional line

And the successor runs at its baked path inside a build of the agent Dockerfile at the PR head, reporting the pinned version and a bundled Codex binary at least as new as the succession requires

And the predecessor is removed only by a later PR that cites a real Codex-provider factory dispatch that ran on the successor

And a succession that skips any of those parts MUST NOT merge

## Scenario: a livespec contract change ships an additive surface bump

Given livespec releases a new version that adds a new spec rule covered by a new shared check

And this library's `compat` block in `.livespec.jsonc` still pins the previous livespec release

When a contributor opens a bump-pin pull request against this library declaring the new pinned livespec tag

Then the PR adds the new check module under `livespec_dev_tooling/checks/<new-slug>.py` with a paired test

And the PR bumps `pyproject.toml`'s `version` field with a `feat:` Conventional Commit

And `release-please` opens a corresponding release PR at its next release window that cuts the next MINOR version

## Scenario: a breaking change to an existing check's CLI ships as a MAJOR bump

Given an existing check module's argv contract is changing in a backwards-incompatible way (e.g., a new required positional argument)

When a contributor opens the change as a `feat!:` Conventional Commit (or includes a `BREAKING CHANGE:` footer)

Then `release-please` opens a release PR that cuts the next MAJOR version

And the release notes call out the breaking change so every consumer's bump-pin PR addresses the new argv contract explicitly

## Scenario: self-application catches a regression before release

Given this library's `master` branch is green and a contributor opens a PR that mutates a shared check's logic

And the mutation introduces a subtle regression detectable only when the check runs against this library's own source tree

When CI runs `just check` against the PR's working tree

Then the self-application failure surfaces the regression at PR time

And the PR cannot merge until the regression is fixed and the check is green against this library's own source

## Scenario: a check attempts forbidden network I/O

Given a contributor writes a new check that reaches out to a remote HTTP endpoint

When CI runs the `no-network-io` gate (the gate that asserts every check stays within the local filesystem + project-local subprocess envelope; sketch only — the gate may itself be tested by a sandboxed firewall fixture or by AST inspection)

Then the gate fails the build

And the PR cannot merge until the network call is removed per `constraints.md` §"No network I/O"

## Scenario: a blessed declared-absent spelling parses to a distinct variant carrying its reason

Given a consumer declares a union role key as one of the four declared-absent inline tables with a non-empty payload

When the configuration loader reads that block

Then the key MUST resolve to a variant distinguishable from every other declared-absent variant

And the payload MUST be retrievable from the parsed value rather than requiring a reader to consult the TOML comment

## Scenario: a declared-absent variant with an empty payload is rejected at load

Given a consumer declares a union role key with a blessed variant name but an empty or whitespace-only payload

When the loader reads that block

Then loading MUST fail with an error naming the key and every legal spelling

## Scenario: the legacy empty spelling on a union key is rejected at load

Given a consumer declares a union role key as a bare `[]` or `""`

When the loader reads that block

Then loading MUST fail with a `ConfigParseError` naming the key

And the diagnostic MUST name every legal spelling for that key

And the emptiness MUST NOT be reported as a sanctioned opt-out

## Scenario: an empty clean role key makes its consuming check stricter, not blinder

Given a consumer declares `io_trees` as a bare `[]`

When the catch-position and domain-raise checks run

Then they MUST inspect the consumer's full first-party universe

And the number of files inspected MUST be non-zero

And no file MUST be wholesale exempt by virtue of that empty declaration

## Scenario: an unarmed-until payload naming a closed work item is a conformance failure

Given a consumer declares a union role key as `unarmed_until` whose payload names a work item that is closed

When the conformance verifier runs

Then it MUST report a failure identifying the consumer, the key, and the item

And the failure MUST state that the declaration claims pending work that is already complete

## Scenario: a stale pin whose bump PR never opened escalates once the release ages past the settle window

Given a fleet member's pin is behind the source repository's latest release

And NO bump pull request for that latest release is open in that member

And the latest release's `published_at` is more than the settle window in the past

When the pin-currency row is evaluated in the release fan-out preflight

Then the row MUST report an error-severity finding

And the diagnostic MUST state that no bump pull request exists and MUST name the release's age

And the same condition evaluated in the per-PR CI job or the scheduled central sweep MUST be reported at warning severity with the identical diagnostic

## Scenario: a stale pin inside the settle window with no bump PR stays a warning

Given a fleet member's pin is behind the source repository's latest release

And NO bump pull request for that latest release is open in that member

And the latest release's `published_at` is within the settle window

When the pin-currency row is evaluated in any context, including the release fan-out preflight

Then the row MUST report the finding at warning severity

And the finding MUST NOT move any exit code and MUST NOT exclude the member from the release fan-out

## Scenario: an unparseable pin file is a finding, never a passing row

Given a fleet member carries a file at a path a known pin format claims

And the walk finds that file and cannot parse its contents

When the pin-currency row for that format is evaluated

Then the row MUST NOT report a passing outcome

And the row MUST report a finding naming the member and the unparseable file

And the finding MUST be distinguishable from that member carrying no pin of that format at all

And the finding MUST be error severity in the release fan-out preflight and warning severity in every other evaluating context

## Scenario: an unparseable member .livespec.jsonc is a tenant-connection finding, never a skip

Given a fleet member's committed `.livespec.jsonc` is present and does not parse

When the tenant-connection consistency row is evaluated for that member

Then the row MUST NOT report a skip or a passing outcome

And the row MUST report a finding naming the member and its `.livespec.jsonc`

And the finding MUST be error severity in the release fan-out preflight and warning severity in every other evaluating context

## Scenario: a healthy App installation budget yields a fresh exactly-scoped token

Given the GitHub App installation's REST core and GraphQL remaining budgets meet the caller's configured minima

And the caller requests a specific owner and repository set

When the caller invokes the `github-rate-budget-token` Action

Then the Action MUST probe the installation budget with a minimum-scope token

And it MUST mint a second token only after the healthy probe

And the output token MUST preserve exactly the requested owner and repository scope

And both tokens MUST retain normal end-of-job revocation

## Scenario: a healthy preflight but deficient final token is not exposed

Given the minimum-scope probe reports REST core and GraphQL budgets at or above the configured minima

And the freshly minted exact-scope final token reports either budget below its configured minimum

When the Action validates the final token before exposing it

Then the Action MUST wait and re-probe the final token under the aggregate wait budget remaining after preflight

And it MUST NOT expose the final token until both budgets meet their minima

## Scenario: a deficient App installation budget waits for the later reset

Given either the REST core or GraphQL remaining budget is below its configured minimum

And the deficient resources advertise different reset times

When the caller invokes the `github-rate-budget-token` Action

Then the Action MUST wait until the later deficient reset plus the configured cushion and deterministic seed-derived jitter

And it MUST re-probe both budgets after waiting

And it MUST mint the downstream token only after both budgets meet their minima

## Scenario: an App installation budget does not recover inside the wait bound

Given a deficient App installation budget remains below its configured minima

And the next required wait would exceed the configured aggregate maximum

When the budget gate evaluates the next wait

Then the Action MUST fail with `rate-budget-not-restored`

And it MUST NOT mint a downstream token

## Scenario: an App budget probe cannot authenticate or reach GitHub

Given the budget probe receives a transport, authentication, or non-success HTTP failure

When three total fetch attempts have failed with the specified retry delays

Then the Action MUST fail with `probe-unusable`

And it MUST distinguish that failure from a healthy probe reporting exhausted quota

## Scenario: an App budget probe returns a malformed rate-limit payload

Given GitHub returns a successful response that lacks a required core or GraphQL remaining or reset field

When the budget gate validates the response

Then the Action MUST fail with `rate-budget-malformed`

And it MUST NOT wait or mint a downstream token from an indeterminate budget

## Scenario: JIT replacement is immediate but installation-budgeted

Given a completed JIT runner creates deduplicated replacement demand

And the installation-wide point budget permits another admission

When the controller rescans demand

Then it MUST admit the replacement without an unconditional per-runner delay

And it MUST account for the mint pair against the shared installation budget

## Scenario: JIT startup batch immediately admits all permitted demand within the half-budget point burst

Given startup observes current deduplicated runner demand

And repository logical ceilings, remaining physical capacity, and the startup point budget permit a non-zero set of demand

When the controller reconciles fleet demand

Then it MUST immediately admit every current demand item in that permitted set in a tight loop without an unconditional sleep

And it MUST admit at most 450 of the 900 REST points per minute, or about 45 complete mint pairs

And it MUST refill further demand only from recorded budget accounting

And it MUST NOT exceed the 450-point startup budget even when more demand remains

## Scenario: JIT throttle opens one shared circuit

Given a JIT mint receives a `403` or `429` response or valid retry guidance

And other repository demand remains queued

When the controller classifies the response

Then it MUST open one installation-wide circuit using the later valid guidance boundary

And it MUST retain queued demand and healthy registered runners

And it MUST resume only through a permitted budgeted recovery admission

## Scenario: JIT fleet capacity borrows fairly without exceeding 482 runners

Given each repository's logical ceiling is bounded to a small multiple of its fair share, so queued work beyond that bound waits at the forge

And unused capacity exists under the host-wide physical cap

When the controller computes admissions

Then each repository desired admission MUST be min(queued jobs, doubled repository logical ceiling, fair share of remaining host-wide capacity)

And repositories MAY borrow unused fair capacity

And fleet active runners MUST never exceed 482 or imply 964 capacity

## Scenario: JIT circuit state survives restart without a reburst

Given a persisted JIT controller has an open circuit or exhausted retry record

When its service manager restarts the supervisor

Then it MUST recover that shared state before admitting demand

And it MUST NOT create a new startup burst or an infinite restart loop

## Scenario: a routed job reads the warm cache and cannot write it

Given the populator has published a current generation of the cargo and uv warm caches on the host

And a job pod for a routed repository starts on the pool with no change to that repository's workflow files

When the job's work volume is provisioned with the current uv generation already seeded into it as a private copy, and the job container's postStart points the package manager at the host-served cargo cache

Then the job's dependency sync MUST resolve from the cache without contacting the package index

And a path the job can reach MUST NOT resolve to a shared inode of a warm tree, so a write from inside the job to a seeded file MUST land in the job's own volume and MUST leave the shared generation unchanged

And the job MUST still be able to create a new entry beside the seed

And a `cache.warm-copy` span with `build.cache.hit` true MUST be emitted for each tier

## Scenario: a job's compilation-cache writes are refused

Given the host compilation cache is reachable from a job pod through its read-only endpoint

When the job compiles a crate that is not in the cache

Then the crate MUST compile locally in the job

And the resulting object MUST NOT appear in the shared cache

And a write issued with the pod's credentials MUST be refused by the backend

## Scenario: a cache fault degrades a job to cold and never fails it

Given the warm-cache tree is absent or unreadable on the node

When a job pod starts

Then the job MUST run to its own outcome with cold caches

And a `cache.warm-copy` span with `build.cache.hit` false and a non-empty `build.cache.error` MUST be emitted

## Scenario: a canary job runs cold and is tagged

Given the pool's canary fraction is one job in N

When a job is selected as the canary by the pool's deterministic rule

Then every cache tier MUST be skipped for that job

And every cache span for that job MUST carry `build.cache.kill_switch` equal to `canary`

And the job's timings MUST be queryable against non-canary jobs of the same repository and phase

## Scenario: a routed job sets up its actions from the pool's action-archive cache, and falls back to a download when an archive is missing

Given the pool's action-archive cache holds the archive of every `uses:` action ref pinned on the default branches of the routed repositories

When a routed job whose `uses:` actions are all in the cache starts on a node that holds the cache

Then the job's Set up job step MUST set up each action from the private seed in its own work volume, and its log MUST show no download from the forge's archive host

And a routed job on a `runner-only` node MUST download its actions and run to its own outcome

And when a newly pinned action ref reaches a routed repository's default branch, the cache MUST hold its archive after the next populator run

And a job whose `uses:` action is absent from the cache, or whose cache is unreadable, MUST download that action and run to its own outcome

And under the fleet kill switch every job MUST download its actions as it would without the tier

## Scenario: a routed job's checkout fetches only the objects its git object seed lacks, and falls back to a full fetch when the seed is missing

Given the pool's git object seed holds the default-branch and tag objects of every routed repository

When a routed job whose repository's seed is present in its work volume runs `actions/checkout` with `fetch-depth: 0`

Then the checkout repository's own object store MUST name that repository's seeded object directory as its git alternate, placed by the pool's runner container hook, and the job container's environment MUST NOT name the seed

And a git repository the job creates outside its checkout MUST resolve only its own objects, so a commit it reads by its own ref is the commit it wrote

And the checkout MUST transfer from the forge only objects absent from the seed, and MUST produce the same work tree and refs as a checkout without the seed

And a job whose seed is missing or unreadable MUST fetch from the forge as it would without the tier and run to its own outcome

And a routed job on a `runner-only` node MUST fetch from the forge and run to its own outcome

And under the fleet kill switch every job MUST fetch from the forge as it would without the tier

## Scenario: a stale warm-cache generation fires the trigger

Given the populator has not published a generation for longer than twice its schedule interval

When the host's liveness path emits the generation-age gauge

Then the stale-generation value trigger MUST fire with a runbook naming the populator

## Scenario: a compilation-cache warm build skipped as busy past two populate intervals fires the lag trigger

Given a repository's default-branch head has moved past the commit its compilation-cache warm set was last built from

And the pool's admitted-job count stayed above the populator's threshold, so every populate run for longer than two populate intervals skipped that repository's compilation-cache warm build as busy

When the host's liveness path emits that repository's consecutive skipped-busy count and warm-set lag

Then the populate manifest MUST show that repository's consecutive skipped-busy count, the commit and toolchain its warm set was last built from, and a lag start time no later than the first of those skipped runs

And the warm-set lag value trigger MUST fire for that repository, and its description MUST name the repository, the warm-set lag and the consecutive skipped-busy count as the fields it reports

And the populator MUST NOT have started a build for that repository while the admitted-job count was above the threshold

## Scenario: rebuilding a lagging compilation-cache warm set clears the lag trigger

Given the warm-set lag value trigger is firing for a repository

When a populate run builds that repository's warm set from its current default-branch head and toolchain and records that build in the compilation cache, or finds that commit and toolchain already recorded there

Then the populate manifest MUST show that repository's consecutive skipped-busy count as zero, no lag start time, and its current default-branch head and toolchain as the commit and toolchain its warm set was last built from

And the warm-set lag value trigger MUST stop being met for that repository within one trigger evaluation window of the next emission

## Scenario: a failed compilation-cache warm build ends the busy-skip streak but keeps the lag start time

Given the populate manifest records a lag start time and a positive consecutive skipped-busy count for a repository

When a populate run's compilation-cache warm build for that repository fails

Then the populate manifest MUST show that repository's consecutive skipped-busy count as zero and the same lag start time

And the warm-set lag value trigger MUST stop being met for that repository within one trigger evaluation window of the next emission, and MUST NOT be met again until its consecutive skipped-busy count again reaches the number of populate runs the populator's schedule starts in two populate intervals

## Scenario: every k3s pool node's load is visible and a silent node fires its dead-man

Given the k3s cluster lists three nodes and each node's collector was converged by `ansible/ci-pool.yml`

When a pod in the factory namespace runs on one of them and another node's kubelet stops answering

Then the fleet observability surface MUST show every node's kubelet CPU and memory usage attributed by `k8s.node.name`

And the factory pod's usage rows MUST carry the node the API server scheduled it on and its namespace

And the silent node's dead-man trigger MUST fire while the other nodes' dead-man triggers stay quiet

## Scenario: an OOM-killed or unschedulable factory pod is visible with its reason and fires its trigger

Given the k3s cluster's emitters were converged by `ansible/ci-pool.yml`

When a container in the `factory` namespace is terminated with reason `OOMKilled` and another factory pod stays Pending because the scheduler cannot place it

Then the fleet observability surface MUST show the terminated container's reason `OOMKilled` attributed by `k8s.namespace.name`, `k8s.pod.name` and `k8s.node.name`

And the Pending pod MUST be readable together with its `FailedScheduling` event and the scheduler's stated reason, joined on the pod's namespace and name

And the factory OOM-or-crash-loop trigger MUST fire, and the factory pending-pod trigger MUST fire once the pod has been Pending for more than 10 minutes

## Scenario: a factory namespace near its quota and a saturated ClusterQueue are each readable and the quota trigger fires

Given the `factory-runs` ResourceQuota and every Kueue ClusterQueue are reported by an emitter converged by `ansible/ci-pool.yml`

When the `factory` namespace's pod count stays at or above 90 percent of `factory-runs`' hard value for 2 hours and a gate ClusterQueue has pending workloads with its CPU usage equal to its nominal quota

Then the fleet observability surface MUST show `factory-runs` used against hard per resource attributed by `k8s.namespace.name`

And that queue's pending count, admitted count and per-flavor CPU usage against nominal quota MUST be readable by queue name

And the factory ResourceQuota trigger MUST fire

## Scenario: an unready API server or a failing datastore fires its trigger

Given the API server readiness probe and the datastore gauges were converged by `ansible/ci-pool.yml`

When the API server's `etcd` readiness check fails for 3 consecutive minutes

Then the fleet observability surface MUST show the failing check by name with the probe's latency

And the API-server-unready trigger and the datastore trigger MUST both fire

## Scenario: a lease PUT's latency is readable apart from every other API-server request

Given the control-plane emitter is converged on `poweredge-xubuntu`

When 15 minutes pass with the API server serving lease renewals

Then the `livespec` environment's metrics dataset MUST hold `apiserver_request_duration_seconds` rows with `verb` = `PUT`, `resource` = `leases` and `host.name` = `poweredge-xubuntu` within that window

And those rows MUST NOT carry a `subresource`, `scope`, `group`, `version`, `component` or `dry_run` attribute

## Scenario: API-server 504 responses are counted by verb and resource

Given the API server's `/metrics` reports `apiserver_request_total` rows with `code` = `504` for `verb` = `PUT`, `resource` = `leases` under two different `scope` values, beside rows with other codes

When the control-plane emitter runs

Then it MUST send one `apiserver_request_total` data point for `verb` = `PUT`, `resource` = `leases`, `code` = `504` whose value is the sum of those rows

And it MUST NOT send an `apiserver_request_total` data point for any other code

## Scenario: an API server with no 504 responses gets no invented zero

Given the API server's `/metrics` reports no `apiserver_request_total` row with `code` = `504`

When the control-plane emitter runs

Then it MUST NOT send any `apiserver_request_total` data point

## Scenario: a silent cluster-state emitter fires its dead-man

Given the cluster-state emitter has been reporting pod phase rows

When it reports none for 20 minutes

Then its dead-man trigger MUST fire while the pool nodes' dead-man triggers stay quiet

## Scenario: a hand-edited board or trigger is reported by its applier's drift mode and left unchanged

Given every committed board and trigger definition under `ci-runner/observability/` has been applied to the fleet observability surface

When one live trigger's threshold and one live board's panel are edited by hand, and a committed trigger definition's live counterpart is deleted

Then running `apply-triggers.sh` in its drift mode MUST print the edited trigger's name and its threshold field, MUST report the deleted trigger's definition as missing, and MUST exit non-zero

And running `apply-boards.sh` in its drift mode MUST print the edited board's name and the differing panel, and MUST exit non-zero

And neither run MAY send a create, update or delete request, so the hand edits are still live afterwards

And straight after a normal apply, both drift modes MUST report no difference and exit zero

## Scenario: a fabro sandbox hits the shared compilation cache

Given the factory sandbox image sets the compiler wrapper and the host compilation-cache endpoint over the docker bridge

And the factory receiver's allowlist admits `build.cache.*`

When a console dispatch compiles dependency crates the populator already built

Then those crates MUST be served from the shared cache

And the dispatch's `build.cargo-*` spans MUST carry `build.cache.sccache.hit_ratio` greater than zero

## Scenario: a pool node is rebuilt from bare metal by the recipe and its profile

Given `ci-runner/k3s/` carries one node rebuild procedure whose first stage is `ci-runner/k3s/phase0-bare-metal/` and one committed profile per pool node

And a pool node is powered on with empty storage

When an operator runs the procedure naming that node's profile

Then the node's storage layout, base operating system, pinned k3s, and node-local mechanisms MUST reach the profile's declared state with no step performed by hand

And the node MUST join the pool and execute a non-gating job addressed to it alone

And re-running the procedure against the finished node MUST change nothing and MUST refuse every step that would destroy its populated storage

And the rehearsal's outcome MUST be recorded naming the procedure revision and the profile

## Scenario: a factory node keeps its factory label across a control-plane reboot

Given every pool node's committed profile declares `FACTORY_NODE`

And every node whose profile declares `FACTORY_NODE=true` carries the `ci-runner.io/factory=true` label

When the control-plane node is rebooted by the committed reboot playbook and every node re-registers

Then once every node is Ready again, each node whose profile declares `FACTORY_NODE=true` MUST carry `ci-runner.io/factory=true`, and each node whose profile declares `FACTORY_NODE=false` MUST NOT carry it

And that MUST hold with no playbook applied and no command run on any host between the reboot and that observation

## Scenario: a node-loss drill holds one agent node NotReady and restores it without touching its workloads

Given an agent node that is neither the control-plane node nor a Fabro factory host

And a factory sandbox pod runs on that node

When an operator applies the node-loss drill with its confirmation naming that node

Then the drill MUST wait until the node carries no CI runner pod and no gate Job pod before it takes the node's k3s agent down

And the API MUST report the node NotReady for the configured hold, after which the drill MUST restore the node to Ready

And the drill MUST NOT have cordoned, drained, evicted or deleted the factory sandbox pod

And the drill MUST report the times the node went NotReady and became Ready again, and MUST fail unless the node's taints, factory label and admission capacity are unchanged

## Scenario: a container-termination drill produces a crash-looping and an OOM-killed container in a throwaway namespace and deletes it

Given the k3s cluster reached from the control node `vps` and a drill namespace name that the API server does not list

When an operator applies the container-termination drill with its confirmation naming the target host

Then the API server MUST report one container in that namespace waiting with reason `CrashLoopBackOff` after at least 3 restarts and another whose last terminated state carries reason `OOMKilled`

And the drill MUST print its start and end UTC times and the namespace's name

And once the drill exits the API server MUST NOT list that namespace, and no object outside it MUST have been created, modified or deleted

And applying the drill without its confirmation, or with `factory`, `factory-mi-homelab` or an existing namespace configured, MUST exit before any cluster write

## Scenario: a new heading-coverage TODO row absent from the debt register fails the authoring-time armed tier

Given a contributor's staged change adds a `test: "TODO"` heading-coverage row that is not present in the repository's `tests/heading-coverage-debt.json` register

When the authoring-time armed tier of the heading-coverage debt check runs against the staged tree

Then the check fails and identifies the unregistered row, even if its exact H2 heading is genuinely new

And the commit cannot land until the row has real coverage, qualifies for spec-first admission with a matching mechanically generated register entry, or is withdrawn

## Scenario: a heading-coverage TODO row already in the debt register passes the armed tier for an unrelated commit

Given the debt register already contains a `TODO` row the contributor did not author

And the contributor's staged change touches unrelated files

When the authoring-time armed tier runs against the staged tree

Then the pre-existing registered row does not fail the commit

And a commit is judged only on the rows it authors, never on debt it inherited

## Scenario: resolving a heading-coverage TODO to a real test requires removing its debt-register entry

Given a contributor replaces a `TODO` row's `test` with a real integration-tier test id

When the staged change also removes that row from `tests/heading-coverage-debt.json`

Then the debt check passes and the register has shrunk by one row

But when the staged change leaves the resolved row in the register

Then the debt check fails, because the register may only shrink in lockstep with real resolutions

## Scenario: a heading-coverage debt register admits only spec-first growth and fails every other addition

Given a repository with a debt register and a readable comparable pre-change `HEAD`

When a staged change adds a register key for a pre-existing heading, a real-test-to-TODO regression, a dangling key, or a registry-only addition

Then the check MUST fail and identify the ineligible growth

But given a change that introduces an exact H2 heading into the governed live specification and neither that heading nor its coverage key exists at `HEAD`

And no existing H2 heading is removed from that specification file

And its new TODO coverage row names an owner and acknowledges that a real test at the required tier is owed

When mechanical regeneration adds the exact matching key, owner and first-seen date and the authoring check runs

Then the check MUST admit that spec-first debt using repository data alone

And after the change is committed the row MUST remain valid as ordinary registered debt at pre-push and CI without an environment override

And pre-push and CI MUST reject an admitted row whose first-seen date is later than the committer date of the earliest commit whose coverage registry carries that key as TODO, or whose required history evidence is unavailable

And the authoring tier MUST compare an existing first-seen date against `HEAD` and fail a change moving it later rather than reset its age

But a missing or mismatched owner, missing required-tier acknowledgment, or unreadable comparison MUST refuse the admission and identify the failed evidence

And a change removing a heading from that same specification file MUST supply real coverage for replacement headings rather than admitting new debt under a new name

## Scenario: a heading-coverage TODO reason asserting non-testability is rejected while one acknowledging an owed test passes

Given a `TODO` heading-coverage row whose `reason` asserts the heading is not testable, is enforced elsewhere, or is prose without behavior

When `heading_coverage` evaluates the row

Then the check fails, because there is no non-testable category and the reason is a cop-out

But given a `TODO` row whose `reason` acknowledges that a real integration-tier test is owed and names a live owning `work_item`

Then the check passes the row as a legitimate transitional debt

## Scenario: a heading-coverage TODO older than the age bound fails the release tier but passes the per-commit tier

Given a `TODO` heading-coverage row whose first-seen date is older than the repository's configured age bound

When the release tier of the debt check runs

Then the check fails, because the transition has exceeded its mechanical age bound

And when the per-commit tier runs against the same unchanged row

Then the per-commit tier does not fail, because liveness and age are evaluated only at the release tier

## Scenario: with an empty heading-coverage debt register only spec-first-admissible TODO rows pass the per-commit tier

Given the repository's debt register has reached empty

When a staged change introduces a TODO row without satisfying all spec-first admission conditions

Then the per-commit tier MUST fail, including for a pre-existing heading or a real-test-to-TODO regression

But when the same change introduces a genuinely new H2 heading with its matching owned mechanically generated debt entry and required-tier acknowledgment, with no heading removed from that specification file

Then the authoring tier MUST admit it under the same rules as a nonempty register

And scoped authorship, ownership and the acknowledgment MUST remain active at zero rather than becoming permanent exemptions

And stale debt or a closed or nonexistent owner MUST still fail the existing release-tier checks

## Scenario: the heading-coverage debt register regenerates from the live registry and matches byte-for-byte

Given a fixture heading-coverage registry with a known set of `TODO` rows

When the debt register is generated mechanically from that live file

Then the generated `tests/heading-coverage-debt.json` matches the expected register byte-for-byte

And regenerating it a second time MUST produce an identical file, never a hand-authored drift

And adding a genuinely new eligible heading MUST preserve every existing first-seen date while assigning the new row its first-seen date and matching owner

## Scenario: a Fabro instance that names its own binary and home renders a unit that runs them

Given a factory host's `fabro_server_instances` holds one instance that omits `binary_path` and `home_env` and one instance that sets both

When the `fabro_server` role renders each instance's unit

Then the instance that omits both axes MUST render a unit byte-identical to the unit the role rendered before the axes existed

And the instance that sets both MUST render a unit whose `ExecStart` runs that binary and whose `Environment=HOME` is that home

And the role's uniqueness preflight MUST accept the list while no `unit_name`, `home_dir` or `port` repeats, and MUST refuse it when one does

## Scenario: the dev-host play stages each pinned Fabro client build and refuses an unsafe entry

Given a dev host whose inventory declares two `fabro_client_builds` entries, each with a `path`, a staged control-node `source` and its `sha256`

When the dev-host play converges the host

Then each build MUST be present at its `path`, mode 0755, owned by the user the role's owner variable names and that user's primary group, and MUST hash to its declared `sha256`

And a second converge with unchanged inventory MUST change nothing on the host

Given the same host after that converge, and an inventory in which one entry's `source` now hashes to a digest other than its `sha256`

When the dev-host play converges the host

Then the role's converge on that host MUST refuse, naming that entry

And the file at each entry's `path` MUST still be the build the earlier converge installed

Given the same host, which is also the control node, and an inventory in which two entries' paths denote the same file on the host, or an entry's `path` is a symbolic link on the host, or an entry's `path` denotes the same file as a `fabro_server_instances` mapping's `binary_path` on that host, or an entry's `source` resolves to its own `path`

When the dev-host play converges the host

Then the role's converge on that host MUST refuse, naming the entry and the reason, before writing anything on the host

## Scenario: the dev-host play points the PATH client at a declared build and leaves the server binary it used to name untouched

Given a dev host whose inventory declares two `fabro_client_builds` entries and a `fabro_client_path_client` whose `target` is the second entry's `path`

And whose `link` is today a symbolic link to a `fabro_server_instances` mapping's `binary_path`

When the dev-host play converges the host

Then `link` MUST be a symbolic link whose literal target is the second entry's `path`, owned by the role's owner user and that user's primary group

And the file at that `binary_path` MUST hash to what it hashed to before the converge

And a second converge with unchanged inventory MUST change nothing on the host

Given the same host after that converge, with the link at `link` re-owned by another account

When the dev-host play converges the host

Then the converge MUST change only the owner and group of the link at `link`

Given the same host, and an inventory whose `fabro_client_path_client` names a `target` that equals no entry's `path`, or a `link` at which a regular file exists, or a `link` that is a symbolic link to a directory, or a `link` whose leaf is absent and whose parent is a symbolic link to that `binary_path`'s directory, so that it names that `binary_path` once its ancestors are resolved

When the dev-host play converges the host

Then the role's converge on that host MUST refuse, naming the reason, before writing anything on the host

## Scenario: converging the Fabro sandbox envelope never restarts dockerd outside a drained window

Given a factory host whose `/etc/docker/daemon.json` already holds keys the sandbox-envelope role does not own

When the role is converged without the operator's drained-restart selection

Then the systemd slice MUST carry the memory and CPU limits named by the role variables

And `daemon.json` MUST carry `cgroup-parent` naming that slice and every key it held before

And `dockerd` MUST NOT have been restarted, and the pending restart MUST be recorded

## Scenario: the sandbox image warm removes the tags it pulled for an earlier pin once the current pin is present

Given a factory host whose sandbox image warm pulled the tags of an earlier pin into its image store, either a k3s node's containerd store or a Docker factory host's image store

And the store also holds a sandbox image tag the warm did not pull

And a reference in the new pinned set resolves to the same image as one of the earlier-pin tags

And a second earlier-pin tag resolves to the same image as a tag the warm did not pull, and a third resolves to the same image as a tag a container references

When a release bump moves the warm's pinned set and a warm run has pulled every reference of the new pinned set, and no other step of that run fails

Then the store MUST hold every reference of the new pinned set, including the one that shares an image with an earlier-pin tag

And the store MUST NOT hold any tag the warm pulled for the earlier pin that is not in use, unless removing it would delete a reference of the new pinned set

And the tag the warm did not pull MUST still be present

And the tag the warm did not pull that shares an image with the second earlier-pin tag, and the tag the container references, MUST still be present

And the run MUST exit zero

## Scenario: the sandbox image warm keeps an earlier-pin tag that a container still references

Given a factory host whose sandbox image warm pulled the tag of an earlier pin, and a container on that host, in any state, references that tag

When a warm run pulls every reference of a newer pinned set and makes its removal pass

Then the tag the container references MUST still be present in the store

And the run MUST NOT exit non-zero on account of that tag

And a later warm run, made after no container on the host references that tag, MUST remove it

## Scenario: a sandbox image warm run that has not resolved and pulled the whole pinned set removes nothing

Given a factory host whose sandbox image warm pulled the tags of an earlier pin into its image store

When a release bump moves the warm's pinned set, and a warm run either fails to pull at least one reference of the new pinned set or fails to read one source of that pinned set

Then that run MUST NOT remove any tag

And the store MUST still hold every tag the warm pulled for the earlier pin

And a run that failed to read a source MUST exit non-zero, naming that source

## Scenario: a container that starts during a sandbox image warm removal keeps its tag

Given a factory host whose sandbox image warm has pulled every reference of its current pinned set, and is removing a tag of an earlier pin that no container referenced when the warm checked

When a container begins referencing that tag after the check and before the removal completes

Then the warm MUST NOT have passed a force flag to a store whose runtime refuses to remove a referenced image

And the store MUST hold that tag when the run ends

And that run MUST exit non-zero, naming the tag

## Scenario: a sandbox image warm removal the store rejects leaves the tag and fails the run

Given a factory host whose sandbox image warm has pulled every reference of its current pinned set, and it also pulled a tag of an earlier pin that no container references

When the warm's removal pass tries to remove that tag and the store refuses, or the removal errors

Then the tag MUST still be present in the store

And that run MUST exit non-zero, naming the tag

## Scenario: a disabled removal pass leaves every tag the sandbox image warm pulled

Given a factory host whose sandbox image warm has the role variable set that disables its removal pass, and the warm pulled the tags of an earlier pin

When a release bump moves the warm's pinned set and a warm run pulls every reference of the new pinned set

Then the store MUST still hold every tag the warm pulled for the earlier pin

And the store MUST hold every reference of the new pinned set

## Scenario: the sandbox image warm's record of the tags it pulled survives a reboot

Given a factory host whose sandbox image warm pulled the tags of an earlier pin, and whose store also holds a sandbox image tag that was present before the warm first kept its record

When the host reboots after a release bump moves the warm's pinned set, and the next warm run pulls every reference of the new pinned set

Then the store MUST NOT hold any tag the warm pulled for the earlier pin that is not in use

And the tag that was present before the warm first kept its record MUST still be present

## Scenario: an opted-in push from a host that cannot read the gates kubeconfig gates locally

Given a consumer repository whose `[tool.livespec_dev_tooling]` table sets `delegated_gate = true`

And a Linux pushing host where the pushing user cannot read the gates kubeconfig

When a git push of a tree that has no green token runs the pre-push gate

Then the local `just check` fall-through MUST run

And the pre-push gate MUST print a line saying it gated locally

And a gate Job MUST NOT be submitted to the `gates` namespace

## Scenario: an opted-in push from an eligible host completes on a green cluster verdict

Given a consumer repository whose `[tool.livespec_dev_tooling]` table sets `delegated_gate = true`

And a pushing host where the pushing user can read the gates kubeconfig

When a git push of a tree that has no green token runs the pre-push gate

Then a gate Job for the committed tree at the pushing worktree's `HEAD` MUST run in the `gates` namespace

And the push MUST complete only after that Job reports a green verdict

And the green token MUST be recorded for that tree

## Scenario: an opted-in push is refused when no verdict arrives

Given a consumer repository whose `[tool.livespec_dev_tooling]` table sets `delegated_gate = true`

And a pushing host where the pushing user can read the gates kubeconfig

And the cluster's API server is unreachable from that host

When a git push of a tree that has no green token runs the pre-push gate

Then the push MUST be refused

And the local `just check` fall-through MUST NOT run in place of the missing verdict

## Scenario: an authority-reading member of an opted-in push runs on the pushing host and joins the delegated verdict

Given a consumer repository whose `[tool.livespec_dev_tooling]` table sets `delegated_gate = true`

And a pushing host where the pushing user can read the gates kubeconfig

And a member of the repository's check set that declares it reads an authorization held outside the tree

When a git push of a tree that has no green token runs the pre-push gate

Then the gate Job MUST NOT run that member

And the pre-push gate MUST run that member on the pushing host against the committed tree at the pushing worktree's `HEAD`

And the push MUST complete only when the gate Job reports a green verdict and that member passes on the pushing host

And when that member fails or cannot be evaluated on the pushing host, the push MUST be refused with a line naming the member and saying it ran on the pushing host

## Scenario: a push of a tree holding a green token still runs the members that read state outside the tree

Given a consuming repository's worktree with no uncommitted changes whose `HEAD` tree is the tree its green token names

And the check set the pre-push gate's local fall-through runs holds a tree-pure member, a world-reading member, and a member that carries no purity declaration

And the world-reading member fails for that tree

When a git push of that tree runs the pre-push gate

Then the world-reading member and the member that carries no purity declaration MUST run on the pushing host

And the tree-pure member MUST NOT run

And a gate Job MUST NOT be submitted to the `gates` namespace

And the push MUST be refused

## Scenario: a check aggregate member with no purity declaration fails the aggregate

Given a member of livespec-dev-tooling's check aggregate that carries no purity declaration

When livespec-dev-tooling's full `just check` aggregate runs

Then the aggregate MUST exit non-zero

And its output MUST name that member

## Scenario: a second controller cannot reserve the Docker engine install guard while a run is unfinished

Given a factory host whose Docker engine install guard holds a current reservation for run A in phase `observing`

When a second controller invokes `reserve` for run B

Then the reservation MUST be refused

And the refusal MUST print run A's id, its phase and its deadline

And run A's phase, its deadline and its dead-man timer MUST be unchanged

## Scenario: the Docker engine install guard refuses to start without a live dead-man

Given a run in phase `armed` whose deadline has not passed

And the run's dead-man timer unit is not active

When `start` is invoked for that run

Then `start` MUST refuse

And the start permission MUST NOT be created

## Scenario: a Docker engine install guard deadline recorded on an earlier boot counts as passed

Given a run in phase `armed` whose deadline was recorded under a boot id that differs from the current boot id

When `start` is invoked for that run

Then `start` MUST refuse because the deadline has passed

And the start permission MUST NOT be created

## Scenario: a Docker engine install guard confirm that arrives after the deadline loses to the rollback

Given a run in phase `observed` with passing evidence and a current challenge

And the run's deadline has passed

When `confirm` is invoked with the challenge's nonce

Then `confirm` MUST refuse

And the commit marker MUST NOT be written

And a later `rollback` for that run MUST roll it back

## Scenario: a Docker engine install guard run named by the commit marker is finished, never rolled back

Given a run whose commit marker names it while its recorded phase reads `committed`

When `rollback` is invoked for that run

Then `rollback` MUST exit 0 without acting

When `confirm` is invoked for that run without a challenge

Then `confirm` MUST enable and start the three guarded units, stop the dead-man timer and move the run to `confirmed`

## Scenario: a Docker engine install guard rollback phase that keeps killing the driver does not stop the later phases

Given a run in phase `rolling-back` whose job-cancellation phase kills the rollback driver every time it is entered

When the dead-man fires `rollback` four times

Then each of the first three firings MUST end in the job-cancellation phase without writing an outcome, leaving the run `rolling-back`

And on the fourth firing the job-cancellation phase MUST be skipped, its recorded attempts having reached three

And on the fourth firing every phase after job cancellation MUST run and the driver MUST write an outcome

## Scenario: the Docker engine install guard's recover resumes an interrupted publish and rolls back any other uncommitted run

Given a run in phase `publishing` whose commit marker is absent and whose snapshot was already taken

When an operator invokes `recover` for that run

Then `publish` MUST resume for that run and keep the first snapshot

Given a run in phase `started` whose commit marker is absent

When an operator invokes `recover` for that run

Then the run MUST be rolled back

## Scenario: a Docker engine install guard publish resumed after a kill during dpkg -i completes the trigger handler that install activated

Given a run in phase `publishing` whose pre-install audit record is empty and is the most recent one any guard run wrote

And a kill during that run's `dpkg -i` left man-db, which is in no recorded intended set, `half-configured` or `triggers-pending`

And dpkg's log records no `install`, `upgrade`, `remove`, `purge` or `configure` action on a package outside every recorded intended set since that record was written

When publish resumes for that run

Then the package step MUST complete man-db with `dpkg --configure` or `dpkg --triggers-only` named on man-db

And it MUST NOT issue `dpkg --configure -a`

And publish MUST NOT report the inert install published while `dpkg --audit` names any package

Given the same run, and dpkg's log records an `install` action on a package outside every recorded intended set since that record was written

When publish resumes for that run

Then the package step MUST refuse naming man-db

And it MUST NOT run `dpkg --configure` or `dpkg --triggers-only` on man-db

## Scenario: a Docker engine install guard publish resumed after a kill during an intended package's unpack re-unpacks it from its audited archive

Given a run in phase `publishing` whose audited `.deb` files include docker.io

And a kill during that run's `dpkg -i` left docker.io `half-installed` at the audited `.deb`'s version and architecture

When publish resumes for that run

Then the package step MUST run `dpkg --unpack` naming docker.io's audited `.deb` and no other file

And it MUST NOT run `dpkg --configure` on docker.io while docker.io is `half-installed`

And publish MUST finish with `dpkg --audit` empty

Given the same run, and the half-installed docker.io is at a version that no audited `.deb` of the run carries

When publish resumes for that run

Then the package step MUST refuse naming docker.io

And it MUST NOT run `dpkg --unpack` or `dpkg -i`

## Scenario: a Docker engine install guard observation sample ignores pod veths on a bridge the snapshot recorded

Given a run whose interface snapshot records the bridge `cni0`

And during the observation window a new veth appears whose master is `cni0`

When the observer takes a sample

Then the interfaces probe MUST pass for that veth

Given the same run, and a new veth appears whose master is `docker0` and that is not the canary's

When the observer takes a sample

Then the interfaces probe MUST fail naming that veth

## Scenario: a delegated gate Job for a repository missing its declared recipe reports red naming the recipe

Given a consuming repository that switches delegation on and declares a check recipe for its gate

And the committed tree at the pushing worktree's `HEAD` does not provide that recipe

When the gate client submits the gate Job for that tree

Then the gate Job MUST report a red verdict that names the missing recipe

And the gate Job MUST NOT have run any recipe that only livespec-dev-tooling declares

And the push MUST be refused, never completed

## Scenario: a delegated gate run that reaches no verdict emits a no-verdict outcome event

Given a consumer repository whose `[tool.livespec_dev_tooling]` table sets `delegated_gate = true`

And a pushing host where the pushing user can read the gates kubeconfig

And the cluster's API server is unreachable from that host

When a git push of a tree that has no green token runs the pre-push gate

Then the push MUST be refused

And the gate client MUST emit exactly one outcome event whose outcome is `no-verdict`

And that event MUST carry the repository's name, the gated tree's hash, and the gate Job's name

## Scenario: a delegated gate verdict is unchanged when its outcome event cannot be delivered

Given a consumer repository whose `[tool.livespec_dev_tooling]` table sets `delegated_gate = true`

And a pushing host where the pushing user can read the gates kubeconfig

And the gate Job for the committed tree at the pushing worktree's `HEAD` reports a green verdict

And no receiver accepts the run's outcome event

When a git push of a tree that has no green token runs the pre-push gate

Then the push MUST complete

And the gate client MUST report the same verdict, and exit with the same status, that it reports when the outcome event is delivered

## Scenario: the fabro-hosts play renders the factory registry from the inventory's factory names

Given `fabro_factory_registry` maps `legacy` to one host's instance with a `docker_host`, and maps `petri` to another host's instance with no `docker_host`

And a `dev_hosts` host whose `/etc/livespec/fabro-factories.json` holds a stale entry named `retired`

When `ansible/fabro-hosts.yml` converges and runs the rendering on that host

Then that host's `/etc/livespec/fabro-factories.json` MUST map `legacy` and `petri` each to an object whose `server` is `https://` followed by the named instance's `canonical_host`

And `legacy`'s object MUST carry that `docker_host` and `petri`'s object MUST carry none

And the file MUST hold no other entry, so `retired` is gone, and MUST be owned by root and world-readable

Given `fabro_factory_registry` is changed so that `petri` names an instance on a third host

When `ansible/fabro-hosts.yml` converges and runs the rendering on that host

Then `petri`'s `server` MUST be `https://` followed by the third host's instance's `canonical_host`, and the previous address MUST be gone

Given the inventory declares no `fabro_factory_registry`

When `ansible/fabro-hosts.yml` converges and runs the rendering on a `dev_hosts` host

Then that host's `/etc/livespec/fabro-factories.json` MUST hold the empty object

Given a `dev_hosts` host whose `/etc/livespec/fabro-factories.json` holds an entry the inventory no longer declares

When `ansible/fabro-hosts.yml` runs with `--tags` selecting no rendering task

Then that host's file MUST be unchanged

Given a `fabro_factory_registry` entry that is <invalid>

When `ansible/fabro-hosts.yml` converges and runs the rendering on any host

Then the play MUST refuse before writing the registry on any host, naming that factory and the reason

Examples of <invalid>: a name that is whitespace only; a `host` that is not an inventory host; a `unit_name` that matches no instance on its `host`; a matched instance whose `canonical_host` is whitespace only; a `docker_host` that is whitespace only

## Scenario: the fabro-hosts play renders each registered factory's run cap from its instance's max_concurrent_runs

Given `fabro_factory_registry` maps `petri` to an instance on another host whose `fabro_server_instances` entry declares `max_concurrent_runs: 20`

When `ansible/fabro-hosts.yml` converges and runs the rendering on a `dev_hosts` host

Then that host's fleet-limit directory, `/home/ubuntu/.local/state/livespec/fleet-limits` by default, MUST hold a world-readable file `petri.max_concurrent_runs` whose single line is `20`

And that host's `/etc/livespec/fabro-factories.json` entry for `petri` MUST carry no capacity key

Given that instance's `max_concurrent_runs` is changed to `16` and nothing else is changed

When `ansible/fabro-hosts.yml` converges and runs the rendering on that `dev_hosts` host and the `fabro_server` role converges that instance

Then `petri.max_concurrent_runs` MUST hold the single line `16`

And that instance's rendered `settings.toml` MUST carry `max_concurrent_runs = 16`

Given a `fabro_factory_registry` entry whose resolved instance declares no `max_concurrent_runs`

When `ansible/fabro-hosts.yml` converges and runs the rendering on any host

Then the play MUST refuse before writing the registry or any run-cap file on any host, naming that factory

## Scenario: the manifest reader accepts an instruction-only adopter and holds it to plugin currency only

Given a `.livespec-fleet-manifest.jsonc` whose `adopters` array holds an entry with `profile` `["instruction-only"]` and `posture` `released`, and another with `profile` `["instruction-only"]` and `posture` `none`

And the released adopter's repository carries no justfile, mise configuration or `.livespec.jsonc`, and its committed `.claude/settings.json` declares `livespecPluginCurrencySuccessor` with a non-empty `mechanism` and `documentedIn`

When the manifest is parsed and the fleet-conformance sweep evaluates its adopters

Then the parse MUST succeed, and the released adopter's adopter plugin-currency row MUST pass with no other row evaluated for it

And the adopter with posture `none` MUST be reported posture-excluded without failing the sweep

Given an adopter entry whose `profile` is <invalid>

When the manifest is parsed

Then the parse MUST fail with the `malformed-adopter` reason

Examples of <invalid>: `["instruction-only", "baseline"]`; `["instruction-only", "orchestrator-plugin"]`; `["instructions-only"]`; the empty list

## Scenario: worktree-reap leaves a worktree that a live process holds

Given a repository with the canonical worktree-discipline pack installed

And a clean secondary worktree whose branch is merged into the base and which is the working directory of a live process

When `just worktree-reap --execute --force` runs

Then that worktree MUST be reported as SKIP with a reason naming the live process's pid

And that worktree MUST remain on disk

## Scenario: worktree-reap never removes a factory-owned source worktree

Given a repository with the canonical worktree-discipline pack installed

And a clean secondary worktree named `fabro-source-<id>` whose head is merged into the base and which no live process holds

When `just worktree-reap --execute --force` runs

Then that worktree MUST be reported as SKIP with a reason saying it is factory-owned

And that worktree MUST remain on disk

## Scenario: dev host retention leaves an in-flight gate run and removes an aged terminal one

Given a governed checkout on the dev host whose `tmp/gate-runs` holds a terminal gate run older than the retention period

And a gate run older than the retention period whose recorded process is still alive

When one run of the dev host retention script completes

Then the terminal gate run's directory MUST be removed

And the live gate run's directory MUST remain in place

And the run's log MUST name the removed directory and the root filesystem's free space before and after

## Scenario: dev host retention removes a dead session's scratch directory and leaves a live one

Given a session scratch directory under `/tmp/claude-<uid>` unmodified for longer than the scratch retention period whose session id no running process carries

And a session scratch directory equally old whose session id a running process carries

When one run of the dev host retention script completes

Then the dead session's directory MUST be removed

And the live session's directory MUST remain in place

And the run's log MUST name the removed directory and the free space of the root filesystem and of `/tmp` before and after

## Scenario: dev host retention removes an aged Codex marketplace backup and leaves the live marketplaces

Given the retention user's `~/.codex/.tmp/marketplaces` holding a `marketplace-backup-*` directory unmodified for longer than the scratch retention period

And a `marketplace-backup-*` directory modified within the scratch retention period

And a live marketplace directory unmodified for longer than the scratch retention period

And no process holding `~/.codex/.tmp/marketplaces/.staging.lock`

When one run of the dev host retention script completes

Then the aged backup directory MUST be removed

And the recent backup directory and the live marketplace directory MUST remain in place

And the run's log MUST name the removed directory

## Scenario: the dev host capacity check alerts when /tmp passes its threshold

Given `/tmp` on the dev host with a used share at or above its configured threshold

And the root filesystem below its threshold

When the capacity check runs

Then it MUST publish one notification to the host's ntfy topic naming `/tmp`, its used share and its free space

And it MUST NOT publish a notification naming the root filesystem

And a second run inside the repeat interval MUST NOT publish another

## Scenario: an opted-in push whose consumer names a private cross-repository sibling clones it with a read-only installation token

Given a consumer repository whose `[tool.livespec_dev_tooling]` table sets `delegated_gate = true`

And whose `.livespec.jsonc` `cross_repo_targets` names a private sibling repository

And a pushing host where the pushing user can read the gates kubeconfig and the fleet GitHub App's credentials

When a git push of a tree that has no green token runs the pre-push gate

Then the gate Job MUST clone that sibling with an installation token scoped to that sibling and to read-only repository contents

And the rendered gate manifest MUST NOT contain that token

And the gate Job MUST run the consumer's recipe with that sibling's clone present

## Scenario: a red master whose re-run passes is classified a flake and never merges a revert

Given `master`'s gate job reports a completed failure on the newest commit

When the reconcile run re-runs the failed jobs once and the re-run passes

Then the run classifies the episode as a flake, MUST NOT merge any revert, and raises one needs-attention issue for the episode

## Scenario: a genuine regression opens a held revert of the earliest red commit with a green parent

Given a red `master` classified as a genuine regression, whose earliest red commit has a green parent and a pull request

When the reconcile run takes its next step

Then it opens a revert pull request with auto-merge held, whose forge-created commit restores the culprit's parent bytes and carries `This reverts commit <culprit sha>.`

## Scenario: a later master commit touching a culprit path blocks the revert

Given a genuine regression whose culprit changed a path that a later `master` commit also changed

When the reconcile run takes its next step

Then it MUST NOT create the revert and raises needs-attention naming the obstructing commit

## Scenario: an unclaimed revert is released as soon as its own CI is green

Given a held revert pull request with no valid fix-forward claim

When the revert's own CI reports green

Then the reconcile run releases the revert for merge

## Scenario: a valid fix-forward claim holds the revert while the fix makes progress

Given a held revert carrying a valid fix-forward claim naming one fix pull request

When the fix makes a forward transition within the stall duration of its current step

Then the reconcile run keeps the revert held

## Scenario: a thrashing fix-forward releases the held revert

Given a held revert carrying a valid fix-forward claim

When the fix repeats red on the same check, adds a commit that does not reduce its failing checks, fails a new check, or merges while `master` stays red

Then the reconcile run releases the revert

## Scenario: a stalled or contested fix-forward releases the held revert

Given a held revert carrying a valid fix-forward claim

When no forward transition occurs within the current step's stall duration, or a second fix pull request is claimed

Then the reconcile run releases the revert

## Scenario: at the hard cap a revert with green CI lands regardless of fix-forward progress

Given `master` has been red longer than the configured hard cap and the revert's own CI is green

When the reconcile run takes its next step

Then it releases the revert even while a valid claim's fix is still making progress

## Scenario: at the hard cap a revert whose CI is not green is not merged

Given `master` has been red longer than the configured hard cap and the revert's own CI is not green

When the reconcile run takes its next step

Then it MUST NOT merge the revert and raises needs-attention

## Scenario: a fix-forward claim from outside the claimant set is ignored

Given a held revert whose only claim comes from an identity that is neither the maintainer's forge login nor the culprit pull request's opener with a `Claimed-By:` line

When the reconcile run takes its next step

Then it ignores the claim and treats the revert as unclaimed

## Scenario: missing or malformed reconciler configuration fails closed to revert-by-default

Given the committed hard cap or a step's stall duration is absent or malformed

When the reconcile run evaluates a held revert carrying a valid claim

Then it does not hold the revert for the claim, and releases it only once its own CI is green

## Scenario: a master red past the threshold with no revert in flight raises needs-attention

Given `master` has been red longer than the configured threshold

And no revert pull request is in flight

When the reconcile run takes its next step

Then it raises needs-attention for the episode

## Scenario: a failed revert-path drill raises needs-attention

Given the scheduled drill reverts a product-implementation change on a throwaway branch

When the drill's revert is not merged green, including when the range gate convicts it

Then the drill raises needs-attention

## Scenario: a fleet member whose master-health shim is missing or drifted fails conformance

Given a fleet member whose master-health reconcile shim is absent or differs from the canonical shim

When fleet conformance evaluates the `workflow-master-health-reconcile` row

Then the row reports an error-severity finding for that member

## Scenario: a dev-tooling release fan-out dispatches only after its sandbox image tags are served

Given a livespec-dev-tooling release T whose livespec-fabro-sandbox semver tags are not yet served by ghcr.io

When the release fan-out runs

Then it MUST send no sibling-released dispatch while any of T's tags is absent

And it MUST dispatch to every unexcluded sibling once all of T's tags are served

## Scenario: a dev-tooling release fan-out whose sandbox image never appears fails naming the missing tags

Given a livespec-dev-tooling release T whose livespec-fabro-sandbox tags are not all served after the 90-minute bound

When the release fan-out reaches that bound

Then the run MUST fail with an annotation naming each missing tag

And it MUST send no sibling-released dispatch

## Scenario: a host at its local-gate slot limit queues the next pytest session

Given a host whose local-gate slot limit is set to 2

And two pytest sessions from fleet worktrees each holding a slot

When a third pytest session starts from another fleet worktree

Then the third session MUST wait instead of running its tests

And it MUST print a line naming the limit and that it is waiting, repeated at least once a minute

And when one of the first two sessions ends, the third session MUST run its tests and report their own result

## Scenario: a slot holder that is killed frees its slot without cleanup

Given a host whose local-gate slot limit is set to 1

And one pytest session holding the only slot while another session waits

When the holding session is killed with SIGKILL

Then the waiting session MUST obtain the slot and run its tests without any cleanup step having run

## Scenario: a pytest session nested under a slot holder takes no second slot

Given a host whose local-gate slot limit is set to 1

And a pytest session holding the only slot

When a test in that session starts pytest in a child process

Then the child session MUST run without waiting for a slot

## Scenario: a host with no local-gate slot limit runs pytest sessions unchanged

Given a host with no local-gate slot limit set

When any number of pytest sessions start from fleet worktrees

Then every session MUST start immediately without waiting for a slot

## Scenario: a consumer's delegated gate finds the mise-pinned tools its gate members invoke

Given a fleet consumer that pins `jq` in its `.mise.toml` and has a gate member that invokes `jq`

And a CI container that pins a `python-rust` sandbox image released by this repository

When a delegated gate Job runs that consumer's gate in that image without running `mise install`

Then `jq` MUST be found on `PATH` in the Job

And the gate member MUST run its verification rather than fail for the tool's absence

## Scenario: factory sandbox environments are named for their toolchain, and a rename never strands a dispatch

Given a running, registry-named `fabro_server_instances` mapping declaring an environment `livespec-ci-k8s` whose image carries the `python-agent` layer, and governed repositories whose committed petri `environment` names it

When the environment is renamed

Then the catalog MUST list `factory-python` beside `livespec-ci-k8s` before any governed repository's committed `environment` names `factory-python`

And `factory-python` MUST carry the same image, resources and provider as `livespec-ci-k8s`

And `livespec-ci-k8s` MUST stay in the catalog while any governed repository's committed `environment` or any non-terminal run on that instance names it

And after the removal, the catalog MUST NOT list `livespec-ci-k8s`, and its only `python-agent` environment MUST be `factory-python`

## Scenario: the fabro_server role deletes an instance's retired sandbox environments

Given a `fabro_server_instances` mapping whose `retired_environments` lists `livespec-ci`, and whose instance's catalog holds `livespec-ci`

When the `fabro_server` role converges that instance while no non-terminal run on it uses `livespec-ci`

Then the instance's catalog MUST NOT list `livespec-ci`

And a second converge of the same mapping MUST succeed and report no change

And a converge while a non-terminal run on that instance uses a listed id MUST fail naming the run and the id, and MUST leave that id in the catalog

And a converge of a mapping that lists one id in both `environments` and `retired_environments` MUST fail before changing anything

## Scenario: an apply refuses a plugin binary whose digest differs from an instance pin, and drift compares live pins to the installed binary

Given a factory host whose `fabro_server_instances` declare sha256 `d93437f0...` for the sandbox provider at `/usr/local/bin/sandbox-driver-kubernetes`

When an apply of the role that installs that plugin carries sha256 `93ca024d...` for the same path

Then the apply MUST fail before the binary is downloaded or moved, naming each disagreeing instance and both digests

And the file at that path MUST be unchanged

And an apply whose plugin sha256 equals every instance's declared pin for that path MUST install the binary

And `just ansible-drift ansible/fabro-hosts.yml` MUST report as drift any instance whose live `settings.toml` sha256 for that provider differs from the sha256 of the installed binary

## Scenario: drift reports a Fabro instance whose resolved setting differs from its declaration

Given a Fabro server instance whose host_vars mapping declares a setting with one value

And that instance's `GET /api/v1/settings` resolving the same setting to a different value

When `just ansible-drift ansible/fabro-hosts.yml` runs against the host

Then the report MUST name the instance, the setting, the declared value and the resolved value as drift

And the instance's live settings MUST be unchanged

And an instance whose settings endpoint cannot be reached MUST be reported as unreachable rather than as matching

## Scenario: an apply on a host missing a role's out-of-band input fails before the role changes anything

Given a role in a committed playbook under `ansible/` that reads a credential through an environment wrapper on the target host

And a target host on which that credential does not resolve

When `just ansible-apply` runs that playbook against the host

Then the role MUST fail at an assert that names the missing credential

And no task of that role that can change the host MUST have run

And a post-apply step of that role which no assert can check MUST be listed in the "Out-of-band" section of the role's `HOST_VARS.md`

## Scenario: a held service converges installed and disabled

Given a host service the maintainer holds disabled, installed by a role whose enable variable is at its held value

When `just ansible-apply` converges the role on the host

Then the service's units MUST be installed, disabled and inactive

And a second converge MUST report no change

And `just ansible-drift` MUST report the service as drift after an operator enables it by hand

## Scenario: a member whose only error findings are stale pins still receives the release dispatch

Given a fleet member whose only error-severity findings in the fan-out preflight are pin-currency staleness findings

When the release fan-out filters its dispatch matrix

Then the member MUST receive the sibling-released dispatch

And the run's exclusion summary MUST name each of those findings for that member

## Scenario: a member with an unparseable pin file or a non-pin error row is still excluded from the release dispatch

Given a fleet member with an error-severity can't-parse pin finding, or an error-severity finding on a row other than a pin-currency row

When the release fan-out filters its dispatch matrix

Then the member MUST be excluded from the dispatch with an annotation naming it and the failing rows

## Scenario: an agent session's foreground commit in a hooked repository is refused and names the detached form

Given a repository whose `.git/hooks/pre-commit` is installed

And an agent session, working in that repository, whose `PreToolUse` hooks include the gate-command guard

When the session issues a `Bash` tool call running `mise exec -- git commit -m "<message>"` in the foreground

Then the guard MUST refuse the tool call with its foreground-gate `check_id`

And the refusal MUST name `run_id=$(mise exec -- just gate-start -- mise exec -- git commit -m "<message>") && mise exec -- just gate-wait "$run_id"`

## Scenario: an agent session's commit dispatched through the detached gate runner is not refused

Given a repository whose `.git/hooks/pre-commit` is installed

And an agent session whose `PreToolUse` hooks include the gate-command guard

When the session issues a `Bash` tool call running `mise exec -- just gate-start -- mise exec -- git commit -m "<message>"`

Then the guard MUST NOT refuse the tool call

## Scenario: an agent session's commit in a repository with no installed commit hook is not refused

Given a repository with no `.git/hooks/pre-commit` and no `.git/hooks/commit-msg` installed

And an agent session, working in that repository, whose `PreToolUse` hooks include the gate-command guard

When the session issues a `Bash` tool call running `git commit -m "<message>"` in the foreground

Then the guard MUST NOT refuse the tool call

## Scenario: an agent session's foreground full-suite pytest on a delegating host is refused and names the gate-start form

Given a repository with `delegated_gate = true`

And an agent session whose user can read the gates kubeconfig

When the session runs `uv run pytest -n 8` in the foreground in that repository

Then the guard MUST refuse the tool call with its full-suite pytest `check_id`

And the refusal MUST name `just gate-start -- uv run pytest -n 8`

## Scenario: an agent session's targeted pytest or a factory sandbox's full suite is not refused

Given a repository with `delegated_gate = true`

When an agent session on a host whose user can read the gates kubeconfig runs `uv run pytest tests/test_one.py` in the foreground

Then the guard MUST NOT refuse the tool call

And when an agent session on a host whose user cannot read the gates kubeconfig runs `uv run pytest -n 8` in the foreground

Then the guard MUST NOT refuse that tool call either

## Scenario: a staged type error refuses the commit before the full pre-commit aggregate

Given a governed repository whose pre-commit hook runs `just check-pre-commit`

And ten staged Python files that the repository's type-checker configuration covers, one of which carries a type-checker error

When a git commit is made

Then the commit MUST be refused within 60 seconds of the commit starting

And the refusal MUST name the file, line and rule of the type-checker error

And the full pre-commit aggregate MUST NOT have started any member

## Scenario: a staged lint error refuses the commit before the full pre-commit aggregate

Given a governed repository whose pre-commit hook runs `just check-pre-commit`

And a staged Python file carrying a lint error that the lint autofix step does not fix

When a git commit is made

Then the commit MUST be refused naming the file, line and rule of the lint error

And the full pre-commit aggregate MUST NOT have started any member

## Scenario: a dev-tooling release bump rewrites the factory-reach image pin with the workflow image pins

Given a repository whose `.github/workflows/ci.yml` pins `ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-v1.110.0` under a job's `container:` block

And whose `ci-runner/k3s/phase2/factory/factory-reach-image.env` carries `FACTORY_REACH_SANDBOX_IMAGE=ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-v1.110.0`

When a livespec-dev-tooling release v1.134.5 bumps the repository's pins

Then the pin autodiscovery walk MUST yield a fabro-sandbox docker image tag record for the env-file line

And the bump commit MUST rewrite both lines to `python-v1.134.5`

## Scenario: a detached gate outlives the caller that launched it and reports its own exit code

Given a checkout carrying the worktree-discipline pack

When `gate-start` launches a gate command that exits with a code from 1 to 127 after the launching shell has returned

And `gate-wait` is issued for the printed run id

Then the run record MUST carry an `exit_code` equal to the gate command's exit code

And `gate-wait` MUST report the state `FAILED` and exit with that same code

## Scenario: a detached gate whose process dies without a verdict reports DIED_WITHOUT_VERDICT and exits 75

Given a detached gate run whose record carries a `pid` and no `exit_code`

And the process named by that `pid` is no longer alive

When `gate-wait` or `gate-status` is issued for that run

Then the reported state MUST be `DIED_WITHOUT_VERDICT`

And the exit code MUST be `75`

And the run MUST NOT be reported as passed

## Scenario: a shared-config write during a detached gate is recorded with writer attribution and marks the run

Given a detached gate run launched from a linked worktree

When a process descended from the gate rewrites the primary checkout's shared `.git/config` `[core]` section while the gate is alive

And that process stays alive until the write-watch has recorded the change

And the changed `[core]` section persists until the gate ends

And the gate completes with an exit code from 0 to 127

Then the run's `config-writes.log` MUST record the write and name the writing process

And the run record MUST carry a `CORE_BARE_FLIP` marker

And `gate-status`, issued after the gate completes, MUST print the marker while still exiting with the gate's own exit code

## Scenario: an idle detached gate run and an idle waiter spawn no per-tick process

Given a detached gate run whose command is alive

And neither the shared `.git/config` nor its lockfile changes

And a `gate-wait` blocked on that run

When the run stays in that state across an observation window

Then the runner MUST spawn no child process on any observation of the config

And the waiter MUST spawn no child process on any poll of the run's state

And `gate-wait` MUST still return within five seconds of the run's `exit_code` appearing

## Scenario: an opted-in commit from a credentialed host runs its replay tests against the staged tree

Given a repository with `delegated_commit_tests = true`

And a committing host whose user can read the gates kubeconfig

And a working directory whose unstaged edits differ from the index

When the developer makes a Red commit

Then the gate Job MUST run the Red leg's staged tests against the tree `git write-tree` names for the index

And the committing host MUST verify that tree hash before honouring the reported outcome

And the committing host MUST run no pytest for that leg

## Scenario: a seat's gate-runner full suite runs as a gate Job by default

Given a repository with `delegated_gate = true`

And a host whose user can read the gates kubeconfig

When a seat runs `gate-start -- just check` in a worktree with uncommitted changes

Then the suite MUST run as a gate Job against a tree that includes those changes

And the run record MUST carry `venue: cluster_job`, the gate Job's name and the tree hash

## Scenario: a full suite spelled as python -m pytest runs as a gate Job

Given a repository with `delegated_gate = true` on an eligible host

When a seat runs `just gate-start -- uv run --no-sync python -m pytest --cov=src`

Then the run MUST record venue `cluster_job`

And it MUST NOT record venue `host_local` with the reason "command outside full-suite set"

## Scenario: a delegated gate-runner run with no cluster verdict ends without a verdict

Given a repository with `delegated_gate = true`

And a host whose user can read the gates kubeconfig

When a seat runs `gate-start -- just check` and the gate Job is lost before it reports

Then the run MUST end as `DIED_WITHOUT_VERDICT` and `gate-wait` MUST exit `75`

And the runner MUST NOT re-run the command on the dev host

## Scenario: a gate-start whose venue selector cannot be imported refuses by name

Given a checkout whose project environment and `python3` both fail to import `livespec_dev_tooling`

When a seat runs `just gate-start -- true` in that checkout

Then `gate-start` MUST start no gate and write no run record

And it MUST print a refusal naming the venue selector, each interpreter it tried and the remedy

And it MUST exit with a code other than `70`

## Scenario: an explicit local gate-runner run is recorded as local

Given a repository with `delegated_gate = true`

And a host whose user can read the gates kubeconfig

When a seat runs `gate-start --local -- just check`

Then the suite MUST run on the dev host

And the run record MUST carry `venue: host_local` and the reason `--local`

## Scenario: a delegated replay leg's trailers name the gate Job and the staged tree

Given a repository with `delegated_commit_tests = true`

And a committing host whose user can read the gates kubeconfig

When the gate Job reports the Red leg's test as failed, with its output

Then the committing host MUST judge the Red expectation from that reported outcome

And the TDD-Red trailers MUST record the output checksum computed from the reported output

And the TDD-Red trailers MUST name the gate Job and the staged tree hash

## Scenario: a delegated replay leg with no verdict falls back to a local run

Given a repository with `delegated_commit_tests = true`

And a committing host whose user can read the gates kubeconfig

When the developer makes a Red commit and the gate Job returns no verdict

Then the committing host MUST run the Red leg's staged tests itself

And the TDD-Red trailers MUST be recorded from that local run, not from the absent verdict

And the hook MUST say that it gated locally

And the commit MUST NOT be refused because the cluster returned no verdict

## Scenario: a commit from a host without the gates credential runs its replay tests locally and says so

Given a repository with `delegated_commit_tests = true`

And a committing host whose user cannot read the gates kubeconfig

When the developer commits

Then the replay gate's test runs MUST execute on the committing host

And the hook MUST say that it gated locally

## Scenario: a delegated pre-commit aggregate gates the staged tree on the cluster

Given a repository with `delegated_pre_commit = true`

And a committing host whose user can read the gates kubeconfig

When a hand commit runs the pre-commit hook

Then the pre-commit aggregate MUST run as a gate Job against the staged tree's hash

And the hook output MUST name that gate Job and the staged tree hash

And a red Job verdict MUST refuse the commit

## Scenario: a delegated pre-commit aggregate with no cluster verdict gates locally

Given a repository with `delegated_pre_commit = true`

And a committing host whose user can read the gates kubeconfig

When a hand commit runs the pre-commit hook and the gate Job cannot be submitted

Then the committing host MUST run the pre-commit aggregate itself

And the hook output MUST say that it gated locally

And the commit MUST NOT be refused because the cluster returned no verdict

## Scenario: a delegated gate Job's Kueue admission wait does not consume its poll budget

Given a delegating host that submits a gate Job to the `gates` namespace

And the Job stays suspended awaiting Kueue admission for less than the admission bound

When Kueue admits the Job and the Job reaches a verdict within the poll budget measured from admission

Then the gate client MUST report that verdict

And the time the Job spent suspended MUST NOT count toward the poll budget

## Scenario: a delegated gate Job never admitted within the admission bound ends without a verdict and is deleted

Given a delegating host that submits a gate Job to the `gates` namespace

When the Job is still suspended awaiting Kueue admission when the admission bound runs out

Then the gate run MUST have no verdict

And the client's output MUST name the Job and say that it was not admitted

And the client MUST delete the Job before it returns

## Scenario: a gate client that stops waiting on an admitted gate Job deletes it

Given a delegating host whose submitted gate Job was admitted

When the poll budget measured from admission runs out before the Job reaches a verdict

Then the gate run MUST have no verdict

And the client's output MUST name the Job and say that it was admitted

And the client MUST delete the Job before it returns

And a refused delete MUST be reported in the output without changing the absent verdict

## Scenario: a delegated gate check suite ending in the pre-commit aggregate is refused

Given a consuming repository whose `[tool.livespec_dev_tooling]` sets `delegated_gate = true`

And declares `gate_check_suite = ["install-worktree-pack", "check-pre-commit"]`

When its shared pre-commit or pre-push check aggregate runs

Then the aggregate MUST fail

And its output MUST name `pyproject.toml`, the key `gate_check_suite`, the final entry `check-pre-commit` and the expected final recipe `check-pre-push`

And the same aggregate MUST NOT fail on that rule when the declared suite ends in `check-pre-push` or in `hook_gate=1 check`, when the key is absent, or when `delegated_gate` is not `true`

## Scenario: a canonical check waived in pyproject.toml is exempt from the aggregate and fleet gates

Given a fleet member whose `pyproject.toml` declares `canonical_check_waivers` under `[tool.livespec_dev_tooling]` with slug `check-heading-coverage` and a non-empty reason

And its `just check` aggregate does not select `check-heading-coverage`

When `check-aggregate-completeness` runs in the member and the fleet-conformance row `canonical-check-slugs-wired` evaluates the member's master tree

Then neither fails on `check-heading-coverage`

And the fleet-conformance run logs the waiver with the member, the slug and the reason

Scenario: a stale waiver fails

Given a member whose `canonical_check_waivers` names `check-file-lloc`

And its `just check` aggregate selects `check-file-lloc`

When `check-aggregate-completeness` runs

Then it fails, naming `check-file-lloc` as a stale waiver

Scenario: a malformed waiver fails

Given a member whose `canonical_check_waivers` holds an entry that has an empty reason, lacks a key, carries an extra key, or gives `slug` or `reason` a non-string value

When the fleet-conformance row `canonical-check-slugs-wired` evaluates the member

Then it fails, naming the entry's slug (or its position when it has no string slug) as a malformed waiver

Scenario: an unreadable member pyproject.toml makes the fleet row skip rather than apply no waiver

Given a member whose `just check` aggregate omits a canonical slug that its `pyproject.toml` waives

And the fleet-conformance run cannot read or parse that member's master-tree `pyproject.toml`

When the fleet-conformance row `canonical-check-slugs-wired` evaluates the member

Then the row skips the member

And it MUST NOT report the omitted slug as a finding

Scenario: an unparseable pyproject.toml applies no waiver in the in-repo check

Given a consumer whose `just check` aggregate omits a canonical slug

And its own `pyproject.toml` cannot be parsed

When `check-aggregate-completeness` runs

Then it applies no waiver

And it fails, naming the omitted slug as missing

## Scenario: a test-only commit runs only its staged tests unless shared test support changed

Given a commit that stages only `tests/test_alpha.py` and no implementation file and no shared test-support file

When the commit-msg `red_green_replay` check runs its suite-green leg

Then it MUST run only the tests in `tests/test_alpha.py`, and MUST NOT run the full suite

## Scenario: a test-only commit that changes shared test support runs the full suite

Given a commit that stages only test files, one of which is `tests/conftest.py`

When the commit-msg `red_green_replay` check runs its suite-green leg

Then it MUST run the full suite

## Scenario: a test-only commit whose staged tests fail is refused

Given a commit that stages only `tests/test_alpha.py`, one of whose tests fails

When the commit-msg `red_green_replay` check runs its suite-green leg

Then the commit MUST be refused

## Scenario: a behaviour-preserving commit runs the full suite, and an empty run is refused

Given a commit that stages `livespec_dev_tooling/foo.py` and no test file, whose `HEAD` carries no Red awaiting a Green

When the commit-msg `red_green_replay` check runs its suite-green leg

Then it MUST run the full pytest suite against the staged tree

And on pytest exit `0` it MUST record `TDD-Suite-Green-Scope: full-suite`, a `TDD-Suite-Green-Output-Checksum` and a `TDD-Suite-Green-Captured-At` trailer

And on any non-zero pytest exit, pytest exit `5` included, the commit MUST be refused with a `suite-red` event

## Scenario: a suite-green run that stops printing output for the stall window is ended

Given `LIVESPEC_SUITE_GREEN_STALL_SECONDS` is `60` and `LIVESPEC_SUITE_GREEN_TIMEOUT_SECONDS` is unset

And the suite-green leg's pytest run prints no new output for 60 seconds

When the commit-msg `red_green_replay` check runs its suite-green leg

Then it MUST kill the run's whole process group, pytest-xdist workers included

And the commit MUST be refused with an event naming the 60-second stall window and `LIVESPEC_SUITE_GREEN_STALL_SECONDS`

And no `TDD-Suite-Green-*` trailer MUST be recorded

## Scenario: a stalled suite-green run names the tests that were still running

Given `LIVESPEC_SUITE_GREEN_STALL_SECONDS` is `60` and `LIVESPEC_SUITE_GREEN_TIMEOUT_SECONDS` is unset

And the suite-green leg's pytest run collects three tests, one of which completes, and another keeps running past 60 seconds without printing output

When the commit-msg `red_green_replay` check ends the run for stalling

Then the refusal event MUST name the seconds elapsed since the run started and that 1 of 3 collected tests had completed

And the refusal event MUST name the node id of the completed test and the instant it completed

And the refusal event MUST name the still-running test, how long it had run and the pytest-xdist worker that ran it

And the refusal event MUST say that the run stalled mid-suite

And the refusal event MUST carry the output the leg had received from the run

## Scenario: a suite-green run that stalls after its last test is reported as a post-last-test stall

Given `LIVESPEC_SUITE_GREEN_STALL_SECONDS` is `60` and `LIVESPEC_SUITE_GREEN_TIMEOUT_SECONDS` is unset

And every test the suite-green leg's pytest run collected has completed, and the run then prints no output for 60 seconds before it exits

When the commit-msg `red_green_replay` check ends the run for stalling

Then the refusal event MUST say that the run stalled after its last test rather than mid-suite

And the refusal event MUST name the node id of the last test the run reported complete and that all of its collected tests had completed

## Scenario: a suite-green run ended before any test completed says that no test had completed

Given `LIVESPEC_SUITE_GREEN_STALL_SECONDS` is `60` and `LIVESPEC_SUITE_GREEN_TIMEOUT_SECONDS` is unset

And the suite-green leg's pytest run completes no test for 60 seconds, because its collection or worker start-up has not finished

When the commit-msg `red_green_replay` check ends the run for stalling

Then the commit MUST be refused with a failed verdict naming the 60-second stall window

And the refusal event MUST say that no test had completed, in place of a last completed test

And no `TDD-Suite-Green-*` trailer MUST be recorded

## Scenario: a long suite-green run that keeps printing output is not ended

Given `LIVESPEC_SUITE_GREEN_STALL_SECONDS` and `LIVESPEC_SUITE_GREEN_TIMEOUT_SECONDS` are unset

And the suite-green leg's pytest run takes 3000 seconds, never going 900 seconds without new output, and exits `0`

When the commit-msg `red_green_replay` check runs its suite-green leg

Then it MUST NOT end the run

And it MUST record the same `TDD-Suite-Green-Output-Checksum` that a 300-second run of the same green suite records

## Scenario: a refused suite-green run names why each test failed

Given a commit whose suite-green leg selects `tests/test_alpha.py`, whose test `test_one` fails with `AssertionError: expected 2`

When the commit-msg `red_green_replay` check runs its suite-green leg

Then it MUST invoke pytest with `--tb=line`

And the `suite-red` event MUST carry a `failure_summary` naming `tests/test_alpha.py::test_one`

And the event MUST carry a `failure_detail` holding the line `tests/test_alpha.py:<line>: AssertionError: expected 2`

## Scenario: a suite-green leg reuses a passing full pre-commit aggregate on the same tree

Given the pre-commit hook of a behaviour-preserving commit has just run the full check aggregate to a passing result on tree `T`

And `git write-tree` names tree `T` for the index when the commit-msg hook runs

When the commit-msg `red_green_replay` check runs its suite-green leg

Then it MUST NOT start a pytest suite run

And it MUST record its `TDD-Suite-Green-*` trailers from the aggregate run, naming that run

## Scenario: a suite-green leg runs the full suite when the pre-commit aggregate judged a different tree or ran partially

Given the pre-commit hook of a behaviour-preserving commit ran the check aggregate on tree `T1`, or ran only part of the aggregate

And `git write-tree` names tree `T2` for the index when the commit-msg hook runs, or the aggregate run did not run the full suite

When the commit-msg `red_green_replay` check runs its suite-green leg

Then it MUST run the full pytest suite against the staged tree

And it MUST record its `TDD-Suite-Green-*` trailers only from that run

## Scenario: a consumer's local pre-commit aggregate run through the shared entry point is reused by its suite-green leg

Given a consumer repository whose `check-pre-commit` recipe runs its local pre-commit aggregate through livespec-dev-tooling's local-aggregate entry point

And a behaviour-preserving commit, one that stages product `.py` with no Red awaiting a Green

And the aggregate exits `0` on tree `T` with no unstaged change and no untracked, non-ignored file, and `git write-tree` names `T` both before and after it

And `git write-tree` names tree `T` for the index when the commit-msg hook runs

When the commit-msg `red_green_replay` check runs its suite-green leg

Then it MUST NOT start a pytest suite run

And it MUST record its `TDD-Suite-Green-*` trailers from that aggregate run, naming that run

## Scenario: the local-aggregate entry point writes no evidence for a failed, dirty or changed tree

Given a consumer's local pre-commit aggregate run through livespec-dev-tooling's local-aggregate entry point for a behaviour-preserving commit, one that stages product `.py` with no Red awaiting a Green

And the aggregate exits non-zero, or the working tree has an unstaged change or an untracked, non-ignored file, or `git write-tree` names a different tree after the aggregate than before it

When the entry point exits

Then it MUST exit with the aggregate's own exit status

And it MUST write no same-tree evidence

And the suite-green leg of that commit MUST run its suite in full

## Scenario: a suite-green leg run emits one outcome event naming whether it reused evidence

Given a commit whose suite-green leg runs, either reusing same-tree pre-commit evidence or starting its own suite run

When the leg finishes, whether green, red or ended

Then it MUST emit exactly one OTLP outcome span naming the repository, the committed tree's hash, the mode `reused` or `ran`, the scope, the outcome and the wall-clock duration

And when the observability receiver cannot be reached, the leg MUST record the same trailers or refusal and exit with the same status

## Scenario: an in-turn sandbox commit whose affected-tests gate passed on the same tree runs only those tests

Given a checkout whose git config sets `livespec.sandboxExempt` to `true`

And a behaviour-preserving commit whose pre-commit hook ran the affected-tests gate through livespec-dev-tooling's affected-tests record entry point, which recorded exit `0`, the selected test paths `tests/test_alpha.py` and `tests/test_beta.py`, and tree `T`

And `git write-tree` names tree `T` for the index when the commit-msg hook runs

When the commit-msg `red_green_replay` check runs its suite-green leg

Then its suite run MUST cover only `tests/test_alpha.py` and `tests/test_beta.py`, and MUST NOT be the full suite

And on pytest exit `0` it MUST record `TDD-Suite-Green-Scope: affected-tests` with trailers naming the recorded gate run

And it MUST NOT record `TDD-Suite-Green-Scope: full-suite`

## Scenario: an affected-tests record outside a sandbox, or for a failed, empty or different run, leaves the full suite in place

Given a behaviour-preserving commit whose pre-commit hook recorded an affected-tests gate run through livespec-dev-tooling's affected-tests record entry point

And at least one of these holds: the checkout's git config does not set `livespec.sandboxExempt` to `true`; the recorded run exited non-zero; the recorded run selected no test path; or the recorded tree differs from the tree `git write-tree` names for the index when the commit-msg hook runs

When the commit-msg `red_green_replay` check runs its suite-green leg

Then it MUST run the full suite

And on pytest exit `0` it MUST record `TDD-Suite-Green-Scope: full-suite`

## Scenario: a test loop over os.environ fails the ambient-environment check on every host, while a single-expression rewrite passes

Given a Python file under the declared `tests_tree_prefix` containing `for name in [n for n in os.environ if n.startswith("GIT_")]:` with `monkeypatch.delenv(name)` on the next line

When `no_ambient_environment_loops` runs, on a host whose environment carries a `GIT_` variable and on a host whose environment carries none

Then the check fails on both hosts, naming the file, the loop's line and a single-expression rewrite

And a `# pragma: no cover` comment on the loop's body line does not change that verdict

And the same loop written over a name bound from `dict(os.environ)` also fails

But given the same filtering written as one simple statement, such as `_ = [monkeypatch.delenv(n) for n in os.environ if n.startswith("GIT_")]`

Then the check passes that file on both hosts

## Scenario: the whole-suite coverage run prints its thirty slowest test phases

Given a `just check-per-file-coverage` run whose test suite has more than thirty test phases

When the run's test suite completes

Then the run's output MUST list the thirty slowest test phases of that run, each with its duration

## Scenario: a token-bearing response on a model the LLM-spend price table does not list is sent at a marked fallback price

Given the shared LLM-spend price table lists `gpt-6.1-sol` and does not list `gpt-7-sol`

When an emitter sends a response on `gpt-7-sol` that carries non-zero tokens to the `llm-spend` dataset

Then the event's `cost_usd` MUST be non-zero and computed at `gpt-6.1-sol`'s list price

And the event MUST carry `spend.price_fallback` = `true` and a `cost_note` naming `gpt-6.1-sol`

And a response on `gpt-6.1-sol` itself MUST be sent at its list price with no fallback marker

## Scenario: an interactive seat launched by class runs with the model and effort its profile class names

Given the committed fleet seat profile defines a class `monitor` with model `claude-sonnet-5-5`, effort `medium` and an auto-compact threshold below the model's context ceiling

When the committed seat launcher starts a seat of class `monitor`

Then the session MUST be started with model `claude-sonnet-5-5`, effort `medium` and that auto-compact threshold, all taken from the profile

And a launch naming a class the profile does not define MUST be refused before any session starts, naming the class

## Scenario: a pipefail script reports a match in a large input as a match

Given a shell script under `ci-runner/` that runs with `set -o pipefail` and tests whether its input contains a pattern

When the input contains the pattern near its start and is larger than 64 KiB

Then the script MUST report the pattern as present

And its verdict MUST be the same as for a 200-byte input that contains the pattern

## Scenario: a radar that lists the same target twice fails just check

Given the committed `RADAR` lists tenant `livespec-dev-tooling`, id `livespec-dev-tooling-abc123` at index 2 and again at index 5

When `just check` runs

Then the aggregate MUST fail

And the failure MUST name `livespec-dev-tooling-abc123` and both indexes

## Scenario: a radar consumer refuses an item already covered by a listed plan

Given the committed `RADAR` lists `plan` entry `livespec-dev-tooling-p1` and, at a later index, `item` entry `livespec-dev-tooling-p1.3`

And `livespec-dev-tooling-p1.3` has a null `parent` field and no `parent-child` edge

When a radar consumer calls the radar load entry point

Then the call MUST refuse with a defect naming `livespec-dev-tooling-p1.3` as a child of `livespec-dev-tooling-p1`

And the consumer MUST receive no radar entries

## Scenario: a related edge does not block a radar target

Given item `I` has a `relates-to` edge to an open item `J`, a `discovered-from` edge to an open item `K`, and a `blocks` edge to a closed item `L`

And `I` is listed on the radar with an empty `blocked_by`

When readiness is computed for `I`

Then `I` MUST be ready

And no open item MUST be named as its blocker

## Scenario: a closed radar entry is reported as done and does not stall its consumers

Given the committed `RADAR` lists `plan` entry `livespec-dev-tooling-p2`, whose epic has just closed

When a radar consumer calls the radar load entry point

Then the call MUST return the radar with a finding naming `livespec-dev-tooling-p2` as done

And readers MUST treat `livespec-dev-tooling-p2` as needing no work

And `just radar-validate` MUST fail naming `livespec-dev-tooling-p2` as a closed entry

## Scenario: a blocked radar target names each open blocker by tenant and id

Given item `livespec-dev-tooling-i1` has a `blocks` edge to the open item `livespec-dev-tooling-j1` and a `blocks` edge to the closed item `livespec-dev-tooling-j2`

And `livespec-dev-tooling-i1` is listed on the radar with `blocked_by` `livespec:livespec-k1`, which is open, and a `relates-to` edge to the open item `livespec-dev-tooling-j3`

And `livespec-dev-tooling-c1` is listed on the radar and is closed

When readiness is computed for `livespec-dev-tooling-i1` and for `livespec-dev-tooling-c1`

Then `livespec-dev-tooling-i1` MUST be NOT READY

And its blockers MUST be exactly `livespec-dev-tooling:livespec-dev-tooling-j1` and `livespec:livespec-k1`

And `livespec-dev-tooling-c1` MUST be DONE, and MUST NOT be reported as READY or NOT READY

## Scenario: a Honeycomb query spec whose result lacks an expected column fails its contract test

Given a committed query spec that expects column `p90_cpu_seconds` of type float

When the contract test runs that spec against live Honeycomb and the result has no `p90_cpu_seconds` column

Then the contract test MUST fail naming the spec and the missing column

## Scenario: an unreachable Honeycomb endpoint yields flagged fallback decisions

Given the MCP endpoint override names a host that does not resolve

When an admission tick runs

Then every decision in that tick MUST carry `inputs: fallback` with the failure reason

And the coordinator printout MUST show a `HONEYCOMB UNREACHABLE since <UTC>` line above radar entry 1

And the radar array MUST be unchanged

## Scenario: a per-tick query set larger than the budget constant fails the unit tests

Given the per-tick budget constant is N

When a change adds query specs so that one tick would run N + 1 queries

Then the unit test that counts the per-tick set MUST fail naming the count and the constant

## Scenario: an execution target's pressure stall readings are queryable in livespec by host

Given the pressure emitter is converged on `gmktec-xubuntu`

When 15 minutes pass with the host running

Then the `livespec` environment's metrics dataset MUST hold `some` and `full` readings for cpu, memory and io with `avg10`, `avg60` and `avg300` values stamped `host.name` = `gmktec-xubuntu` within that window

## Scenario: a host with no pressure file makes the emitter fail rather than report zero

Given a host whose kernel exposes no `/proc/pressure/memory`

When the pressure emitter runs

Then the emitter MUST exit non-zero with a log line naming `/proc/pressure/memory`

And no memory pressure datapoint MUST be emitted for that host in that run

## Scenario: a configured cgroup's CPU pressure is queryable in livespec by cgroup and host

Given the pressure emitter is converged on `poweredge-xubuntu` with `system.slice/k3s.service` configured

When 15 minutes pass with the host running

Then the `livespec` environment's metrics dataset MUST hold the metrics `livespec.cgroup.pressure.cpu.{some,full}.{avg10,avg60,avg300}` stamped `cgroup` = `system.slice/k3s.service` and `host.name` = `poweredge-xubuntu` within that window

## Scenario: a configured cgroup with no pressure file makes the emitter fail rather than report zero

Given a host configured with a cgroup whose `cpu.pressure` file does not exist

When the pressure emitter runs

Then the emitter MUST exit non-zero with a log line naming that `cpu.pressure` file

And no datapoint MUST be sent for that host in that run

## Scenario: a host with no configured cgroup emits only host pressure

Given a host whose pressure telemetry configuration sets no cgroup list

When the pressure emitter runs

Then the request it sends MUST hold that host's pressure datapoints

And the request MUST NOT hold any `livespec.cgroup.pressure.cpu.*` datapoint

## Scenario: the dev host's available memory is queryable in livespec

Given the dev host's collector is converged from the merged configuration

When 15 minutes pass

Then the `livespec` environment's metrics dataset MUST hold `system.linux.memory.available` stamped with the dev host's `host.name` within that window

## Scenario: the radar admission function decides every ready target identically on identical inputs

Given a radar whose readiness snapshot reports targets `A`, `B` and `C` READY and target `D` NOT READY

And a fixed inventory file, thresholds file and Honeycomb snapshot

When the admission function runs twice on those same inputs

Then the two outputs MUST be identical byte for byte

And each output MUST hold exactly one `admit` or `refuse` decision for each of `A`, `B` and `C`, and none for `D`

And every `refuse` decision MUST name its rule id and the numbers it compared

## Scenario: the highest-ordered ready target is admitted to any execution target with headroom for its cost

Given radar targets `A` at index 1 and `B` at index 2 are READY, and their run class has a p90 cost of 600 CPU-seconds, 4 GiB peak memory and 1 slot

And execution target `gmktec-xubuntu` has headroom of 0 slots, and execution target `hp-xubuntu` has headroom of 1 slot, 2000 CPU-seconds and 8 GiB

When the admission function runs

Then `A` MUST be admitted to `hp-xubuntu` with its rule id

And `B` MUST be refused with a rule id and the slot numbers compared for each execution target

## Scenario: a lower-ordered target does not backfill an execution target a higher-ordered waiting target could use

Given radar target `A` at index 1 is READY with a run class that needs 8 GiB peak memory, and target `B` at index 2 is READY with a run class that needs 1 GiB

And execution target `hp-xubuntu` has 6 GiB of memory headroom and accepts both run classes, and execution target `poweredge-xubuntu` has 12 GiB and accepts only `B`'s run class

When the admission function runs

Then `A` MUST be refused naming 8 GiB against 6 GiB on `hp-xubuntu`

And `B` MAY be admitted to `hp-xubuntu` or `poweredge-xubuntu`, because `A` could use neither

And when `hp-xubuntu`'s memory headroom is raised to 9 GiB, `A` MUST be admitted to `hp-xubuntu` and `B` MUST NOT be admitted to `hp-xubuntu` ahead of it

## Scenario: an execution target stays closed until its reading falls back past the exit threshold

Given the thresholds file sets memory pressure `enter` 20 and `exit` 10 for `hp-xubuntu`

And the Honeycomb snapshot's memory-pressure series for `hp-xubuntu` reads 5, then 25, then 15, oldest first

When the admission function runs with a READY target whose run class `hp-xubuntu` accepts

Then the function MUST NOT admit it to `hp-xubuntu`

And the refusal MUST name the memory-pressure rule and the numbers 15 and 10

And when the series instead ends 25, then 8, the function MUST treat `hp-xubuntu` as admitting again

## Scenario: a new execution target is admissible from one inventory entry

Given an inventory fixture listing `gmktec-xubuntu` and `hp-xubuntu`, both without headroom for a READY target's run class

When one inventory entry for `hetzner-xubuntu` accepting that run class is added, with its thresholds-file values and a Honeycomb snapshot giving it headroom

Then the admission function MUST admit the target to `hetzner-xubuntu`

And the change MUST touch no file other than the inventory file, the thresholds file and the snapshot fixture

## Scenario: a runner-only profile opens a node to CI without planning a storage change

Given a pool node profile declaring `CI_NODE_FACILITIES=runner-only`, `ADMISSION_CAPACITY_C=8`, no CI-closing taint, no physical volume, volume group, logical volume or tier, and a runner work-volume directory on an existing mount

When the bare-metal storage stage plans against that profile

Then the plan MUST contain no mutating command and MUST say that the posture declares no storage

And the profile parser MUST accept the profile

## Scenario: a runner-only profile that keeps its CI-closing taint is refused

Given a pool node profile declaring `CI_NODE_FACILITIES=runner-only` with `NODE_TAINTS` carrying a `node-role/ci` record

When the profile parser reads it

Then the parser MUST exit non-zero with a message naming `NODE_TAINTS`

## Scenario: a runner-only profile with zero admission capacity is refused

Given a pool node profile declaring `CI_NODE_FACILITIES=runner-only` with `ADMISSION_CAPACITY_C=0`

When the profile parser reads it

Then the parser MUST exit non-zero with a message naming `ADMISSION_CAPACITY_C`

## Scenario: a runner work volume on a runner-only node is provisioned under the profile's directory and starts unseeded

Given a converged `runner-only` node whose profile names a runner work-volume directory

When the volume provisioner provisions a runner work volume on that node

Then the volume MUST be created under that directory

And the volume MUST carry no seeded warm tree and MUST be writable by the runner

## Scenario: the cohort churn-slot quota equals the sum of the nodes' declared capacities

Given the committed pool node profiles

When the Kueue cohort churn-slot quota is read from the committed manifests

Then it MUST equal the sum of every pool node profile's `ADMISSION_CAPACITY_C`

## Scenario: a runner pod is placed on the node with the lowest churn-slot use, whatever its CPU and memory requests

Given two pool nodes that both carry the `k3s-role=arc-runner-host` label and no CI-closing taint
And node A has a lower fraction of its declared churn-slot capacity in use than node B, and at least one free churn slot
And node A's requested CPU and memory fractions from non-runner pods are both higher than node B's

When a new CI runner pod is admitted

Then it MUST be placed on node A

## Scenario: a runner pod is never placed on a node with no free churn slot

Given two pool nodes that both carry the `k3s-role=arc-runner-host` label and no CI-closing taint
And every churn slot node A declares is in use
And node B has at least one free churn slot

When a new CI runner pod is admitted

Then it MUST be placed on node B

## Scenario: a node takes runner pods up to its declared churn-slot capacity and no fewer

Given a pool node that carries the `k3s-role=arc-runner-host` label and no CI-closing taint
And its non-runner pods request most of its CPU and most of its memory
And it has free churn slots
And no other pool node has a free churn slot

When CI runner pods are admitted one after another

Then the node MUST take runner pods until all of its declared churn slots are in use
And a CPU or memory request of a non-runner pod on it MUST NOT stop a runner pod from being placed there while it has a free churn slot

## Scenario: a runner pod that requests no churn slot is placed by the default scheduler

Given a runner scale set whose runner pods request no `ci-runner.io/churn-slot`

When one of its runner pods is created

Then the pod MUST name the default scheduler
And no node's churn-slot use MUST change

## Scenario: a runner pod stranded by a down runner scheduler is handed to the default scheduler

Given the runner scheduler has had no ready replica for 60 seconds
And a runner pod that names it is Pending with no node and no scheduling gate

When the fail-open reconciler next runs

Then the pod's runner MUST be re-pointed at the default scheduler and the pod deleted
And the runner controller MUST recreate the pod under the same runner name, naming the default scheduler
And it MUST be placed on a node with a free churn slot
And the scale set's own template MUST stay unchanged

## Scenario: a runner pod still gated by Kueue is left alone during a scheduler outage

Given the runner scheduler has had no ready replica for 60 seconds
And a runner pod that names it still carries a scheduling gate

When the fail-open reconciler runs

Then that pod MUST NOT be recreated

## Scenario: a failed read of the runner scheduler changes nothing

Given the runner scheduler's Deployment cannot be read because the API call failed

When the fail-open reconciler runs

Then no runner and no runner pod MUST change
And the run MUST exit non-zero

## Scenario: runner pods select the committed runner scheduler profile and every other pod keeps the default profile

Given the CI stack converge has applied the committed runner scheduler profile to the cluster

When a CI runner pod that requests a `ci-runner.io/churn-slot`, a factory sandbox pod and a gate pod are created

Then that CI runner pod MUST name the committed runner scheduler profile as its scheduler
And the factory sandbox pod and the gate pod MUST be scheduled by the cluster's default scheduler profile
And the cluster's default scheduler profile MUST carry the same plugin configuration it carried before the converge

## Scenario: an unknown CI-facilities posture is refused

Given a pool node profile declaring `CI_NODE_FACILITIES=partial`

When the profile parser reads it

Then the parser MUST exit non-zero with a message naming `CI_NODE_FACILITIES` and the value `partial`

## Scenario: a runner-only profile with no work-volume directory is refused

Given a pool node profile declaring `CI_NODE_FACILITIES=runner-only` with an empty `RUNNER_WORKVOL_DIR`

When the profile parser reads it

Then the parser MUST exit non-zero with a message naming `RUNNER_WORKVOL_DIR`

## Scenario: a closed profile with admission capacity or without its CI-closing taint is refused

Given a pool node profile declaring `CI_NODE_FACILITIES=none` with `ADMISSION_CAPACITY_C=4`, or with no `node-role/ci` record in `NODE_TAINTS`

When the profile parser reads it

Then the parser MUST exit non-zero with a message naming `ADMISSION_CAPACITY_C` or `NODE_TAINTS` respectively

## Scenario: a runner-only node receives the runner container hook and still takes factory sandboxes

Given a pool node profile declaring `CI_NODE_FACILITIES=runner-only` and `FACTORY_NODE=true`

When the node-provisioning stage is applied to that node

Then the node MUST carry the runner container hook the stage installs on a `full` node

And the node MUST carry the `ci-runner.io/factory=true` label, and a factory sandbox pod MUST schedule on it

## Scenario: a job on a runner-only node reads the pool's host-served caches over the node network

Given a converged `runner-only` node and the pool's dependency proxies and shared compilation cache running on another pool node

When a CI job runs on the runner-only node

Then the job MUST reach the dependency proxies and the shared compilation cache over the pool's node network

And the job MUST start with no seeded warm tree in its work volume

## Scenario: a move from none to runner-only is rehearsed by its provisioning apply

Given a pool node whose profile changes from `CI_NODE_FACILITIES=none` to `CI_NODE_FACILITIES=runner-only`

When the node-provisioning apply takes the node to executing a CI job

Then that apply MUST count as the profile change's rehearsal without emptying the node's storage

And the owning ledger item MUST record the apply run, the procedure revision and profile it ran with, the runner pod and node, and the job id

## Scenario: a move to or from full still needs an empty-storage rehearsal

Given a pool node whose profile changes its `CI_NODE_FACILITIES` to or from `full`

When the change is applied without a rehearsal from empty storage

Then the node's rebuild procedure MUST be treated as unproven for that node

## Scenario: a Codex plugin hook command that mentions CLAUDE_PLUGIN_ROOT without a braced plugin-root path fails the producing repository's gate

Given a repository that tracks `.claude-plugin/.codex-plugin/plugin.json` and a default `.claude-plugin/hooks/hooks.json` whose `SessionStart` event declares the command `python3 "$CLAUDE_PLUGIN_ROOT/hooks/start.py"`

When `python -m livespec_dev_tooling.checks.codex_hook_reconcilable` runs in that repository

Then it MUST exit `4`

And it MUST emit a `fail` finding with `failure_mode` `no_plugin_root_path` whose `manifest` is `.claude-plugin/.codex-plugin/plugin.json`, whose `event` is `SessionStart`, and whose `command` is that command

## Scenario: a Codex plugin hook entrypoint missing from the plugin payload fails the producing repository's gate

Given a repository that tracks `livespec/.codex-plugin/plugin.json` with a `hooks` entry of `./hooks/hooks.json`, whose `Stop` event declares the command `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/gone.py"`, and that tracks no file `livespec/hooks/gone.py`

When `python -m livespec_dev_tooling.checks.codex_hook_reconcilable` runs in that repository

Then it MUST exit `4`

And it MUST emit a `fail` finding with `failure_mode` `entrypoint_missing` whose `entrypoint` is `livespec/hooks/gone.py`, and which names the manifest, the `Stop` event and the command

## Scenario: an unparseable Codex plugin hooks file fails the producing repository's gate

Given a repository that tracks a Codex plugin manifest and a default hooks file whose content is not valid JSON

When `python -m livespec_dev_tooling.checks.codex_hook_reconcilable` runs in that repository

Then it MUST exit `4`

And it MUST emit a `fail` finding with `failure_mode` `unparseable_hooks_file` whose `path` names that hooks file

## Scenario: Codex plugin hooks wrapped in shell conditionals with existing plugin-root entrypoints pass

Given a repository that tracks a Codex plugin manifest and a default hooks file declaring one command `if [ -n "${CODEX_THREAD_ID:-}" ]; then exit 0; fi; python3 "${CLAUDE_PLUGIN_ROOT}/hooks/a.py"` and one command `if [ -n "${CODEX_THREAD_ID:-}" ]; then exit 0; fi; bash "${CLAUDE_PLUGIN_ROOT}/hooks/b.sh"`, and that tracks both `hooks/a.py` and `hooks/b.sh` under the plugin root

When `python -m livespec_dev_tooling.checks.codex_hook_reconcilable` runs in that repository

Then it MUST exit `0`

And it MUST emit an `info` event with `manifests_checked` `1` and `commands_checked` `2`

## Scenario: a repository that ships no Codex plugin passes the Codex hook check and reports that it examined nothing

Given a git repository that tracks no file named `plugin.json` under a `.codex-plugin` directory

When `python -m livespec_dev_tooling.checks.codex_hook_reconcilable` runs in that repository

Then it MUST exit `0`

And it MUST emit an `info` event with `manifests_checked` `0` and `commands_checked` `0` and a message saying that the repository ships no Codex plugin hooks

## Scenario: one fleet-wide command adopts the current plugin builds in every fleet member and refuses a split adoption

Given livespec core's fleet manifest lists the members whose local clones are on this host, and each member's committed `.claude/settings.json` enables the orchestrator plugin and the livespec core plugin

And the host's marketplace clone names orchestrator commit X at `origin/<ref>`, for the ref `known_marketplaces.json` records

When the operator runs `just ensure-plugins-fleet X` in livespec-dev-tooling

Then the recipe MUST run each member's own `ensure-plugins` recipe in that member's clone, MUST then take the adopt step for that member with commit X, and MUST print, for every member and every enabled plugin, the installed build before and after, read from `installed_plugins.json` for that member's project path

And when the operator instead names a commit that is not X, the recipe MUST exit non-zero naming both commits, having run no member

And when one member's clone is missing, the recipe MUST still run every other member, MUST name the missing member and its cause, and MUST exit non-zero

And when one member's adopt step exits non-zero, the recipe MUST still run every other member, MUST name that member and its cause, and MUST exit non-zero

And when every member's `ensure-plugins` succeeds but the livespec core plugin is left installed at two different builds across the members, the recipe MUST exit non-zero, naming the plugin, both builds and the members holding each

And for a manifest adopter whose clone exists and whose committed settings enable the orchestrator plugin, the recipe MUST NOT adopt a build there, MUST print one line naming the adopter, its installed build and the adopt step's command, and that line MUST NOT affect the exit code

And when the recipe is run from a linked worktree of livespec-dev-tooling with `LIVESPEC_FLEET_CLONES_ROOT` unset, it MUST resolve members under the parent of the primary checkout

## Scenario: a fleet clone's ensure-plugins keeps its orchestrator build while an orchestrator roll hold is unreleased

Here a roll hold is any build the marketplace offers that no adopt step has yet brought to the clone. A version such as 0.299.0 stands for the build whose `plugin.json` carries it. An install record names that build through its `gitCommitSha`, and a printed line through that commit or its version.

Given livespec-orchestrator-beads-fabro's clone and another fleet member's clone each have orchestrator build 0.299.0 installed, and each clone's livespec-dev-tooling pin names a release carrying the session-reconcile rules

And each member's committed `.claude/settings.json` registers `just ensure-plugins` as a SessionStart hook with the matcher `""`, so it fires on every SessionStart source

When the marketplace offers 0.300.0 and `just ensure-plugins` runs in each clone

Then each clone's `installed_plugins.json` orchestrator record MUST still name 0.299.0

And each recipe MUST print one line naming the plugin, the installed 0.299.0, the record's `lastUpdated` value and `just adopt-orchestrator-build`, MUST reconcile every other enabled plugin, and MUST exit 0

And when the operator runs `just adopt-orchestrator-build livespec-orchestrator-beads-fabro <0.300.0 commit>`, that clone's record MUST name 0.300.0, the recipe MUST print 0.299.0 before and 0.300.0 after, and the other member's record MUST still name 0.299.0

And when the marketplace then offers 0.301.0 and `just ensure-plugins` runs in the livespec-orchestrator-beads-fabro clone, that clone's record MUST still name 0.300.0

And when the operator runs `just adopt-orchestrator-build` naming the other member and the 0.300.0 commit while the marketplace offers 0.301.0, the recipe MUST exit non-zero naming both commits, and that member's record MUST still name 0.299.0

And when the operator runs `just adopt-orchestrator-build` naming a clone that does not exist, or a clone whose committed settings do not enable the plugin, it MUST exit non-zero naming the cause

And when `claude plugin update` exits non-zero, or exits 0 with the install record's `gitCommitSha` not the named commit, the recipe MUST exit non-zero naming the cause

And when `just adopt-orchestrator-build` names an absolute path to a linked worktree, it MUST act on the install record whose project path is that worktree

And when a member that enables the orchestrator plugin has no install record for its project path, including a new linked worktree, `just ensure-plugins` there MUST install the offered 0.301.0, even when its marketplace fetch failed and the marketplace clone already holds 0.301.0

And when the artifact probe of a member's installed orchestrator build answers that it fails verification, `just ensure-plugins` there MUST repair it and MUST print the build before and after

And when that probe does not answer, or only another enabled plugin fails verification, `just ensure-plugins` MUST run no install or update command for the orchestrator plugin and its record MUST be unchanged, and an unanswered probe MUST be reported as a finding with a non-zero exit

And a scan of this library's recipes, hooks, verbs and skills and of fleet members' committed `.claude/settings.json` MUST find no project-scope plugin update or install outside `ensure-plugins`, `just adopt-orchestrator-build` and `just ensure-plugins-fleet`, and no enabled automatic plugin update

## Scenario: an orchestrator build adopted outside ensure-plugins is reported and never downgraded

Given a fleet member's orchestrator build was moved to 0.300.0 by a path other than `just adopt-orchestrator-build` or `just ensure-plugins-fleet`

And the marketplace offers 0.299.0

When that member's SessionStart hook runs `just ensure-plugins`

Then the member's orchestrator record MUST still name 0.300.0

And the recipe MUST print one line naming the plugin, the installed 0.300.0 and the record's `lastUpdated` value, and MUST exit 0

## Scenario: a default-branch push routes to the master runner target and a pull request does not

Given this repository's `ci.yml` gating jobs read `CI_RUNNER_LABELS_MASTER` ahead of `CI_RUNNER_LABELS` for `push` events, with the hosted literal as the last term

When `CI_RUNNER_LABELS_MASTER` names a self-hosted target and a commit is pushed to master

Then every gating job of that push run MUST run on the target `CI_RUNNER_LABELS_MASTER` names

And every gating job of a pull-request run opened at the same time MUST run on the target `CI_RUNNER_LABELS` names

And when `CI_RUNNER_LABELS_MASTER` is deleted, the next push run's gating jobs MUST run on the target `CI_RUNNER_LABELS` names

And the last term of every gating job's `runs-on` expression MUST be a GitHub-hosted literal

## Scenario: a failing test the run did not touch is retried on its own and reported as a flake

Given a repository that loads livespec-dev-tooling's flake-retry pytest plugin

And a failing test whose closure, dotted module names and literal-named paths are all absent from the run's change set

When that test fails on its first attempt and passes on a later one

Then the plugin MUST re-run only that test, in the same session, at most 3 more times and 60 seconds apart, and the session MUST pass

And the terminal summary MUST list the test under `FLAKE-RETRIED` with its attempts and outcome, `tmp/flake-retries/` MUST hold one JSON line for its node id, and under GitHub Actions a `::warning` annotation MUST name it

## Scenario: an untouched test that fails every attempt still fails the session

Given a repository that loads livespec-dev-tooling's flake-retry pytest plugin

And a failing test the run's change set does not touch

When that test fails on its first attempt and on each re-run

Then the plugin MUST re-run it exactly 3 times, 60 seconds apart, and the session MUST fail

And the `FLAKE-RETRIED` block MUST report the test's final outcome as failed

## Scenario: a re-run test's record and summary carry each failed attempt's failure text

Given a repository that loads livespec-dev-tooling's flake-retry pytest plugin

And a failing test the run's change set does not touch, whose first attempt fails with a failure text longer than 4000 characters and whose second attempt passes

When the session ends

Then the test's JSON line under `tmp/flake-retries/` MUST carry a `failures` list with exactly one entry, holding the first 4000 characters of that attempt's failure text, marked as cut

And the `FLAKE-RETRIED` block MUST show, beneath the test's node id, the first non-empty line of that attempt's failure text

## Scenario: a failing test the run touched fails at once with no retry

Given a repository that loads livespec-dev-tooling's flake-retry pytest plugin

And a change set that contains a module in a failing test's in-repository import closure, a path or file name that closure names, or a file inside a directory that closure names

When that test fails

Then the session MUST fail on that first failure, and the plugin MUST NOT re-run the test

## Scenario: a failing test the run touched is named in a withheld-retry block

Given a repository that loads livespec-dev-tooling's flake-retry pytest plugin

And a change set that contains `.github/workflows/ci.yml`

And a failing test whose closure names `.github/workflows/ci.yml` through a string literal

When that test fails

Then the session MUST fail on that first failure, and the plugin MUST NOT re-run the test

And the terminal summary MUST print a `FLAKE-RETRY-WITHHELD` block naming the test's node id and `.github/workflows/ci.yml`, and under GitHub Actions a `::warning` annotation MUST name `FLAKE-RETRY-WITHHELD` and the node id

## Scenario: a failing test that shares only an ancestor directory name with the change set is retried

Given a repository that loads livespec-dev-tooling's flake-retry pytest plugin

And a failing test whose closure names `ci-runner/k3s/phase2/gates/render-gate-job-exit-tests.sh` through consecutive string-literal path segments

And a change set whose only path under `ci-runner/` is `ci-runner/k3s/phase2/factory/DERIVATION.md`

When that test fails on its first attempt

Then the plugin MUST treat the test as untouched and re-run it on its own, exactly as for any untouched failing test

## Scenario: a failing test whose closure names a changed file only under a temporary root is retried

Given a repository that loads livespec-dev-tooling's flake-retry pytest plugin

And a failing test whose closure names `.github/workflows/ci.yml` only through `root / ".github" / "workflows" / "ci.yml"`, where `root` is a directory built from `tmp_path`

And a change set that contains `.github/workflows/ci.yml`

When that test fails on its first attempt

Then the plugin MUST treat the test as untouched and re-run it on its own, exactly as for any untouched failing test

## Scenario: a failing test that copies a repository directory into a temporary root is still touched

Given a repository that loads livespec-dev-tooling's flake-retry pytest plugin

And a failing test whose closure copies `REPO_ROOT / "ci-runner"` into `tmp_path / "ci-runner"`, where `REPO_ROOT` is assigned `Path(__file__).resolve().parents[1]`

And a change set that contains `ci-runner/k3s/x.sh`

When that test fails

Then the session MUST fail on that first failure, and the plugin MUST NOT re-run the test

## Scenario: a change set that touches the build or the plugin disables every retry

Given a repository that loads livespec-dev-tooling's flake-retry pytest plugin

And a change set that contains `pyproject.toml` or `uv.lock` other than as a version-only release change, `justfile`, a `conftest.py` or the plugin itself, or a change set that cannot be computed, or a failing test whose closure holds a module that cannot be parsed

When any test in the session fails

Then the plugin MUST NOT re-run any test in that session

And the terminal summary MUST print a `FLAKE-RETRY-WITHHELD` block naming the reason, and under GitHub Actions the plugin MUST emit a `::warning` annotation naming it

## Scenario: a version-only release change leaves an untouched failing test retried

Given a repository that loads livespec-dev-tooling's flake-retry pytest plugin

And a change set in which `pyproject.toml` differs from its base only in the `[project]` `version` value and `uv.lock` differs from its base only in the `version` value of the repository's own package entry, as a release-please release commit makes

And a failing test whose closure names neither file

When that test fails on its first attempt

Then the plugin MUST re-run it on its own, exactly as for any untouched failing test

And the terminal summary MUST NOT print a `FLAKE-RETRY-WITHHELD` block

## Scenario: a version-only release change still touches a test that names the changed file

Given a repository that loads livespec-dev-tooling's flake-retry pytest plugin

And a change set in which `pyproject.toml` differs from its base only in the `[project]` `version` value

And a failing test whose closure names `pyproject.toml` through a string literal

When that test fails

Then the session MUST fail on that first failure, and the plugin MUST NOT re-run the test

## Scenario: a config-value-only change of .livespec.jsonc leaves a test that names no changed key retried

Given a repository that loads livespec-dev-tooling's flake-retry pytest plugin

And a change set in which `.livespec.jsonc` differs from its base only in the value of a key on the committed config-value fast-path list and in its comments

And a failing test whose closure names `.livespec.jsonc` but neither that key's dotted path nor its final segment

When that test fails on its first attempt

Then the plugin MUST re-run it on its own, exactly as for any untouched failing test

## Scenario: a structural or unlisted change of .livespec.jsonc still touches every test that names the file

Given a repository that loads livespec-dev-tooling's flake-retry pytest plugin

And a change set in which `.livespec.jsonc` adds a key, or changes the value of a key that is not on the committed config-value fast-path list

And a failing test whose closure names `.livespec.jsonc`

When that test fails

Then the session MUST fail on that first failure, and the plugin MUST NOT re-run the test

## Scenario: every retried failure files one root-fix work item

Given `tmp/flake-retries/` holds records for two node ids, one of which already has an open root-fix work item

When the host-side flake reader runs

Then it MUST file exactly one root-fix work item, for the node id that had none

## Scenario: a re-run test's record reaches the host-side reader as a CI artifact

Given the coverage job of this repository, livespec, livespec-overseer or livespec-orchestrator-beads-fabro, whose pytest session re-runs a test

When the job's pytest step finishes, whether it passed or failed

Then the workflow run MUST carry an artifact named `flake-retries` or `flake-retries-<suffix>` holding that job's `tmp/flake-retries/` records

## Scenario: a CI job that re-ran no test publishes no flake-retry artifact

Given the coverage job of one of those repositories, whose pytest session re-runs no test

When the job's publishing step runs

Then the workflow run MUST carry no artifact from that job named `flake-retries` or `flake-retries-<suffix>`, and that step MUST NOT fail the job

## Scenario: the replay legs never retry the Red test and never accept a final failure

Given a repository that loads livespec-dev-tooling's flake-retry pytest plugin

When the red-green-replay Red leg runs its staged failing test

Then the plugin MUST NOT re-run it

And when a Green or suite-green replay leg's suite passes after a re-run, the leg MUST accept the summary, while a suite whose final outcome is a failure MUST still be refused

## Scenario: a CI job killed at Set up job by an action-download 429 is re-run with backoff

Given a gating CI job of livespec-dev-tooling that failed at its runner's `Set up job` step

And its log shows the runner's action download refused with `429 (Too Many Requests)`

When the job's workflow run completes

Then the job MUST be re-run automatically after a wait

And a second such failure MUST be re-run after a longer wait, up to three automatic attempts

And a job that failed at any later step MUST NOT be re-run, and its failure MUST stay the run's verdict

## Scenario: a CI job killed at Initialize containers by a registry network error is re-run once

Given a gating CI job of a fleet repository whose caller workflow calls `reusable-ci-infra-rerun.yml`

And the job failed at its `Initialize containers` step before any later step started

And that step's log shows the container registry pull failing with `connection reset by peer`

When the job's workflow run completes

Then the reconciler MUST re-run that job once, within 5 minutes

And it MUST write the run id, the job id and the matched error line to its own run summary

And a second failure of the same job at `Initialize containers` MUST NOT be re-run, and its failure MUST stay the run's verdict

And a job that failed at a later step, or at `Initialize containers` with no registry network error, MUST NOT be re-run, and the summary MUST record it as left for its owner

## Scenario: a merged runner-pool change reaches the live cluster through one committed apply

Given a merged change that adds a runner scale set and its ClusterQueue under `ci-runner/k3s/phase2/`

And the converge tree on the CI server has been refreshed to that change

When the operator runs the committed live-converge apply from the control node

Then the CI stack converge MUST run on the CI server and the apply MUST wait for it

And the new scale set's listener and ClusterQueue MUST exist on the live cluster

And a second run of the same apply MUST report no change

## Scenario: an incident invocation resolves mode before ordinary gate selection

```gherkin
Given an authorized incident item with explicit attempt/phase and exact repository/base/head identity, and ordinary behavior retained as a control
When the operator exercises resolve trusted incident mode and operation identity
Then an expedited invocation resolves its incident item, attempt, phase, repository and base/head into one typed execution context before selecting any gate.
And an emergency revert resolves only against a recorded incident merge and takes precedence over an expedited repair flag.
And normal master and normal factory follow-up force normal mode before interpreting inherited incident flags, including malformed values.
And ordinary invocation preserves existing gate behavior while invalid incident identity produces a named configuration refusal.
```

## Scenario: an expedited local gate skips slow work and preserves fast failures

```gherkin
Given an authorized incident item with explicit attempt/phase and exact repository/base/head identity, and ordinary behavior retained as a control
When the operator exercises select and bound expedited local gates before delegation
Then expedited commit and push select applicable local gates before staging prechecks, autofix, normal evidence lookup, cluster probes or remote submission.
And a known slow or unclassified gate is reported as deferred with its reason instead of launching the normal full aggregate.
And an unknown selected gate that reaches sixty seconds terminates its owned process group and records deferred-timeout.
And a selected fast gate failure refuses the repair with the actual failure while ordinary work retains normal gate selection.
```

## Scenario: focused incident verification cannot satisfy normal validation

```gherkin
Given an authorized incident item with explicit attempt/phase and exact repository/base/head identity, and ordinary behavior retained as a control
When the operator exercises capture focused incident tests and touched-file coverage without normal cache reuse
Then incident verification executes changed or directly related tests and reports coverage under existing thresholds only for the cumulative touched executable paths.
And incident proof records one manual reproduction with expected and observed outcome alongside the focused test and coverage evidence.
And focused collection uses isolated evidence keyed by mode, scope and exact tree while normal consumers reject partial incident evidence.
And fixture tests of enforcement implementations retain their real positive and negative behavior when incident context is inherited.
```

## Scenario: incident commit provenance remains verifiable on normal master

```gherkin
Given an authorized incident item with explicit attempt/phase and exact repository/base/head identity, and ordinary behavior retained as a control
When the operator exercises validate incident commit receipts and scoped host authorization
Then an expedited repair publishes the exact EXPEDITED_INCIDENT_RESPONSE flag marker beside changed code or tests and binds its commit receipt to the recorded incident attempt.
And normal range and replay readers validate historical incident provenance against the recorded PR, head and landed commits after the label or environment has disappeared.
And an expedited receipt records deferred replay honestly and remains distinct from normal TDD proof.
And a workflow incident requires its scoped host authorization receipt through the credential boundary while the factory retains its existing workflow credential scope.
```

## Scenario: an expedited PR defers coverage and spec work while master runs normally

```gherkin
Given an authorized incident item with explicit attempt/phase and exact repository/base/head identity, and ordinary behavior retained as a control
When the operator exercises select expedited pr checks while forcing complete normal master ci
Then a trusted expedited PR signal selects the declared fast checks while recording coverage and spec enforcement producers and consumers as intentionally deferred.
And mixed CI batches and direct actions execute retained fast targets and publish a required aggregate that distinguishes actual passes, failures and deferred work.
And a new PR head invalidates earlier incident verdicts and label events reconcile mode before permitting merge.
And every normal master push disables both incident flags and selects its complete normal job graph regardless of PR labels, markers or ambient configuration.
```

## Scenario: the first required master leaf failure fences incident recovery

```gherkin
Given an authorized incident item with explicit attempt/phase and exact repository/base/head identity, and ordinary behavior retained as a control
When the operator exercises fence incident recovery actions on an independent first-failure observer
Then an incident merge is admitted only with a durable observer receipt from a known-good released controller independent of the candidate incident tree.
And the first failing required master leaf job emits a trusted recovery action while other jobs in the same original run can continue.
And atomic per-repository action ownership and incident generation validation prevent delayed events or duplicate delivery from mutating a corrected attempt.
And recovery reads its trusted operation receipt and action fence during tenant or credential-wrapper failure and reconciles exact receipts back when service returns.
```

## Scenario: an incident revert preserves later changes without waiting for CI

```gherkin
Given an authorized incident item with explicit attempt/phase and exact repository/base/head identity, and ordinary behavior retained as a control
When the operator exercises apply and merge the complete incident inverse without quality gates
Then the incident recovery controller constructs the inverse of the complete landed multi-commit incident patch against current master and preserves unrelated later edits.
And a changed expected head causes inverse recomputation while a genuine overlap enters an owned rollback-conflict phase.
And the authorized revert merges through the scoped recovery principal without local tests, factory work or pre-merge CI waits.
And recovery records exact action and merge receipts across timeout or restart while ordinary actors retain their existing branch protection obligations.
```

## Scenario: a reverted incident retains its original CI evidence before another attempt

```gherkin
Given an authorized incident item with explicit attempt/phase and exact repository/base/head identity, and ordinary behavior retained as a control
When the operator exercises preserve failed incident ci and corrected attempt evidence
Then revert and replacement events preserve the original master run and its expected job graph through terminal results.
And evidence distinguishes completed, failed, prerequisite-blocked, cancelled and never-created checks and retains missing original-tree work as owned debt.
And a corrected expedited attempt reuses the incident item while preserving its previous PR, merge, revert and evidence identities.
And a new attempt after classification requires a repair or measured resolution rather than relanding unchanged code onto the same unresolved failure.
```

## Scenario: an incident rollback follows released artifacts into consuming repositories

```gherkin
Given an authorized incident item with explicit attempt/phase and exact repository/base/head identity, and ordinary behavior retained as a control
When the operator exercises recover incident releases and adopted fleet consumers
Then an incident release records source-to-tag, image, pin-carrier and installed-consumer attribution before adoption is acknowledged.
And an incident revert fences stale queued adoption and assigns corrective release or rollback work to consumers that already adopted the affected artifact.
And related master or other-PR regressions reopen the same incident attempt chain with stale cleanup actions fenced.
And an irreversible-state change becomes eligible for unattended rollback only when its existing safe compensation is recorded.
```

## Scenario: incident enablement follows complete installed-fleet capability proof

```gherkin
Given an authorized incident item with explicit attempt/phase and exact repository/base/head identity, and ordinary behavior retained as a control
When the operator exercises reconcile the incident surface inventory across installed fleet consumers
Then the fleet audit expands the committed manifest and reports an explicit implemented, deliberately-normal or not-applicable disposition for every incident surface and consumer.
And enablement requires serving-version evidence for gate readers, templates, driver hooks, recovery authorization and independent controller in each applicable consumer.
And consumer closure retains normal factory proof over the cumulative incident scope and all deferred spec and verification obligations.
And the operator can inspect attempts, skip reasons, focused evidence, CI runs, rollback and final factory proof through the incident item identity.
```

## Scenario: a macOS developer host reads the ledger tenant through the loopback forward

Given a macOS developer host that runs no Dolt server

And a per-user LaunchAgent forwarding local `127.0.0.1:3307` to the server host's `127.0.0.1:3307` over SSH

And the checkout's committed `.beads/config.yaml` unchanged

When `/usr/local/bin/with-livespec-env.sh -- bd show <id>` runs from that checkout for an item of this repository's tenant

Then the item MUST be read from the tenant on the server host

And no local beads store, including an `embeddeddolt/` directory, MUST be created on the host

## Scenario: bootstrap names a missing ledger pointer instead of reporting success

Given a checkout of this repository whose `.beads/config.yaml` is present and whose `.beads/metadata.json` is absent

And a developer host that supplies every host toolchain prerequisite

When `just bootstrap` runs in that checkout

Then its output MUST name `.beads/metadata.json` as an unmet ledger pointer

And it MUST exit non-zero

And it MUST NOT report success

## Scenario: bootstrap names a bare python3 that does not satisfy requires-python

Given a developer host whose first `python3` on `PATH` is older than the version `pyproject.toml`'s `requires-python` requires

When `just bootstrap` runs in a checkout of this repository

Then its output MUST name `python3` and the version `requires-python` requires

And it MUST exit non-zero

And it MUST NOT install or replace any interpreter on the host

## Scenario: an opted-in push from an unenrolled macOS host is refused instead of gating locally

Given a consumer repository whose `[tool.livespec_dev_tooling]` table sets `delegated_gate = true`

And a macOS pushing host where the pushing user cannot read the gates kubeconfig

When a git push of a tree that has no green token runs the pre-push gate

Then the push MUST be refused

And the refusal MUST name the missing gates-client enrollment

And the local `just check` fall-through MUST NOT run

And a gate Job MUST NOT be submitted to the `gates` namespace

## Scenario: a gate pytest session that stops making progress ends without a pass

Given a gate run whose pytest session, running pytest-xdist workers, has printed no new output for longer than its stall window

When the stall window elapses

Then the session's whole process group, pytest-xdist workers included, MUST be ended

And the gate MUST end with a verdict or an explicit no-verdict state

And the gate MUST NOT report a pass

## Scenario: a delegated pre-push wait interrupted by host sleep never reports a pass

Given a consumer repository whose `[tool.livespec_dev_tooling]` table sets `delegated_gate = true`

And a pushing host where the pushing user can read the gates kubeconfig

And a push whose gate Job has been submitted for its tree

When the host sleeps while the gate client waits on that gate Job, and then wakes

Then the push MUST complete only on a green verdict that same gate Job reports for that tree

And when the client obtains no verdict from that gate Job, the push MUST be refused and the outcome event MUST be `no-verdict`

## Scenario: the start task refuses an undeclared host before any host change

Given a host argument that the committed homelab-worker host list does not declare

When `just start-homelab-worker-node-container <host>` runs

Then it MUST exit non-zero naming the argument and the declared hosts

And it MUST NOT install a package, create or start a VM, or start a worker container

## Scenario: a VM missing a required capability stops the start task before the worker starts

Given a declared host whose Lima VM does not enforce AppArmor

When `just start-homelab-worker-node-container <host>` runs

Then it MUST exit non-zero

And its output MUST name the AppArmor capability with an actionable remedy

And it MUST NOT start the worker container or submit an enrollment request

## Scenario: rerunning the start task reuses Lima and keeps the VM

Given a declared host with an installed Lima at or above the task's minimum version

And that host's named Lima VM already exists with a persisted worker identity

When `just start-homelab-worker-node-container <host>` runs again

Then it MUST NOT install or upgrade Lima

And it MUST NOT stop, recreate or delete the VM

And the worker MUST keep the persisted identity it had before the rerun

## Scenario: a second worker on the same host is refused

Given a host already bound to the worker `<host-a>-homelab-worker`

When `just start-homelab-worker-node-container <host-b>` runs on that host for a different declared host `<host-b>`

Then it MUST exit non-zero naming the existing worker `<host-a>-homelab-worker`

And it MUST NOT create a second VM or worker container

## Scenario: the start task leaves the host's own tailnet identity unchanged

Given a declared host logged in to the tailnet under its own host name

When `just start-homelab-worker-node-container <host>` runs

Then the task MUST NOT invoke a Tailscale login, logout or settings change on the host

And the worker MUST enroll in the tailnet under the hostname `<host>-homelab-worker`

## Scenario: a newly joined worker carries the admission hold

Given a worker that completes standard TLS bootstrap into the fleet as `<host>-homelab-worker`

When its Node becomes Ready

Then the Node MUST carry the taint `homelab-worker.livespec.dev/admission=hold:NoSchedule`

And a pod without a toleration for that taint MUST NOT be scheduled onto it

## Scenario: a missing bridged-network prerequisite stops the start task before the VM starts

Given a declared macOS host on which Lima's `socket_vmnet` is absent from its root-owned location

When `just start-homelab-worker-node-container <host>` runs

Then it MUST exit non-zero naming `socket_vmnet` with a remedy

And it MUST NOT create or start a VM, or install or modify `socket_vmnet` or the sudoers entry

## Scenario: the worker's node IP is its declared home-LAN address

Given a declared host whose declaration carries a static home-LAN address outside the DHCP pool

When `just start-homelab-worker-node-container <host>` converges its worker

Then the VM's bridged interface MUST carry that address

And the worker's Kubernetes node IP and its pod-network underlay interface address MUST be that address

## Scenario: a joined worker is enrolled in every workload class its architecture can run

Given an arm64 container worker joined through the production join path, a CI class whose job image publishes arm64, and a factory class whose sandbox image publishes only amd64

When the join completes and the admission hold is lifted

Then the worker MUST carry the CI class's node label and churn-slot capacity derived from its allocatable CPU, and the CI class's scale sets MUST tolerate the worker class taint

And the factory class MUST NOT be able to schedule onto the worker, and the join output MUST name the factory class and the arm64 image it lacks

And no per-host values file, profile or inventory entry MUST have changed

## Scenario: a workload is never scheduled onto a node whose architecture its image does not publish

Given a cluster with amd64 nodes and an arm64 worker enrolled in every class whose images publish arm64

When a CI job, a gate job and a factory sandbox whose images publish only amd64 are each admitted

Then each MUST be placed on an amd64 node

And none MUST be placed on the arm64 worker

## Scenario: a worker's per-class capacity is derived from its allocatable resources

Given a joined worker whose node reports its allocatable CPU and memory, and no measured split

When enrollment derives its per-class capacity

Then each class the worker is enrolled in MUST receive an equal share of the allocatable CPU, rounded down and at least one unit

And a class the worker is not enrolled in MUST receive no share, its share being divided among the enrolled classes

And the CI share MUST be expressed in churn slots by the fleet's churn-slot sizing rule

## Scenario: a worker that leaves mid-run loses no work and rejoins on its own

Given an enrolled worker running a CI job, a gate job and a factory run

When the worker leaves the cluster without warning and its host later returns

Then the CI job and the gate job MUST be retried or re-queued onto another node, and the factory run MUST resume or be re-dispatched with its work preserved

And the worker MUST rejoin and re-enroll in the same classes with no operator step

## Scenario: a host declaring no home-LAN address is refused before the VM starts

Given a declared host whose declaration carries no static home-LAN address

When `just start-homelab-worker-node-container <host>` runs

Then it MUST exit non-zero naming the missing declaration

And it MUST NOT create or start a VM

## Scenario: a staged capacity value change commits on schema validation alone

Given a repository whose committed config-value fast-path list names `.livespec.jsonc` `dispatcher.wip_cap`

When a commit stages only a change of `dispatcher.wip_cap` from 4 to 6

Then the pre-commit hook MUST run schema and parse validation of `.livespec.jsonc` and no test suite, and the commit MUST proceed

And a commit that stages `dispatcher.wip_cap` changed to a value the schema rejects MUST be refused, naming `.livespec.jsonc` and `dispatcher.wip_cap`

And a commit that also stages any other changed line MUST run the normal pre-commit aggregate

## Scenario: changing a committed capacity value to another valid value leaves every test passing

Given a repository whose committed `ci-runner` profile sets `ADMISSION_CAPACITY_C` to 8

When `ADMISSION_CAPACITY_C` is changed to 6, a value its schema accepts

Then every test of the repository MUST pass

And a test that checks the profile MUST assert that the capacity is a non-negative integer and that the profiles sum to the cohort quota, not that it equals 8

## Scenario: a stale installed commit-refuse hook names both bodies at the tail of the check output

Given a primary checkout whose `.git/hooks/pre-push` holds bytes that differ from `CANONICAL_HOOK_BODY` from line 12 onward, and whose `.git/hooks/pre-commit` is byte-identical to `CANONICAL_HOOK_BODY`

When `just check` runs `check-primary-checkout-commit-refuse-hook-installed`

Then the check MUST exit 4 with exactly one `non_canonical_body` finding, whose `path` is the absolute path of `pre-push`, whose `installed_sha256` and `canonical_sha256` are the SHA-256 of the installed bytes and of `CANONICAL_HOOK_BODY`, and whose `first_differing_line` is 12

And the last lines of the `just check` output MUST name that `pre-push` path with both SHA-256 values

And with both hooks byte-identical to `CANONICAL_HOOK_BODY` the check MUST exit 0 with no finding

## Scenario: a rule-26 kill-matrix run reports survivors and redundancy candidates

Given a Python package whose suite has three tests, where tests A and B both kill mutant M1, only test A kills mutant M2, and no test kills mutant M3

When `just mutation-kill-matrix` runs over that package

Then the report MUST list A and B as the killers of M1 and A as the only killer of M2

And the report MUST list M3 as a surviving mutant

And the report MUST list B as a redundancy candidate and MUST NOT list A as one

## Scenario: wiring the kill-matrix recipe into the check aggregate is refused

Given a repository whose `just check` aggregate does not reach `mutation-kill-matrix`

When a change adds `mutation-kill-matrix` to the `just check` aggregate

Then the keep-out guard check MUST fail with a finding naming `mutation-kill-matrix` and the `just check` aggregate

## Scenario: the fleet test baseline reports per-repository counts and fleet totals

Given a Python repository whose pytest suite collects 5 tests, a Rust workspace whose `cargo nextest list --message-format json` reports 3 tests, and a repository with 2 `*.test.sh` scripts

When `just fleet-test-baseline` runs over those three clones

Then the JSON document MUST report test counts of 5, 3 and 2 for those repositories, each with its counting command, its timed test command and its wall-clock

And the document MUST report a fleet total test count of 10 and a fleet total wall-clock equal to the sum of the three wall-clocks

And the document MUST name the timing method, the host identity and the toolchain versions

## Scenario: branch protection alignment accepts a required gate held by a ruleset whose only bypass is a GitHub App

```gherkin
Given a repository whose classic protection on the default branch enforces admins, keeps strict off and requires no status check
And an active repository ruleset on that branch requires the all-green gate job with strict off and names only a GitHub App as a bypass actor
When branch_protection_alignment runs with an admin-scoped token
Then the effective required-check set contains the all-green gate and the check exits 0.
And the same configuration with a repository-role bypass actor added to that ruleset fails with failure_mode ruleset_bypass_not_app.
And the same configuration with the ruleset's strict policy enabled fails with failure_mode strict_enabled.
And a ruleset read that fails fails with failure_mode ruleset_unreadable rather than skipping.
```

## Scenario: a coverage-guided kill-matrix run skips tests that do not execute a mutant

Given a Python package with functions F and G, where test T1 executes only F and test T2 executes only G

When `just mutation-kill-matrix` runs over that package

Then each mutant of F MUST be run against T1 and MUST NOT be run against T2

And each mutant of G MUST be run against T2 and MUST NOT be run against T1

And the report MUST name the test-selection method it used

## Scenario: a parallel kill-matrix run reports the same matrix as a single-worker run

Given a fixture package whose tests need no network, at one source revision, where no test's outcome is decided by the per-test timeout

When the kill-matrix engine runs over it once with one worker and once with several workers, with outbound network access disabled

Then both runs MUST complete

And both reports MUST carry the same matrix content: the same mutants, the same killing tests for every mutant, the same surviving mutants and the same redundancy candidates

And each report MUST record the worker count its run used

## Scenario: tests sharing one process each keep their own kill outcome

Given a mutant whose two selected tests run in one shared process, where only the first test fails against that mutant

When the kill-matrix engine runs over the package

Then the report MUST list the first test as killing that mutant

And the report MUST NOT list the second test as killing that mutant

## Scenario: a test whose shared process dies is re-run alone

Given a mutant whose selected tests run in one shared process, where the mutant makes the first test end that process before the second test reports

When the kill-matrix engine runs over the package

Then the engine MUST re-run the second test alone against that mutant

And the report MUST record the second test's own outcome from that re-run

## Scenario: a test that exceeds the per-test timeout against a mutant kills it

Given a mutant that makes a selected test loop forever, where that test passes promptly against the unmutated source

When the kill-matrix engine runs over the package

Then the report MUST list that test as killing that mutant

And the report MUST record the per-test timeout used

## Scenario: a test that fails against the unmutated source is excluded from attribution

Given a fixture package with one test that fails against the unmutated source and a second test that exceeds the per-test timeout against it

When the kill-matrix engine runs over it

Then the report MUST list both tests as baseline failures

And neither test MUST appear as a killer of any mutant

And neither test MUST be listed as a redundancy candidate or an unapplied-coverage test

## Scenario: a mutant the engine cannot apply is recorded and the run continues

Given a fixture package with one mutant that the mutation engine cannot apply, and a test selected only for that mutant

When the kill-matrix engine runs over it

Then the run MUST complete and write its report

And the report MUST list that mutant as unapplied and count it in the unapplied total

And that mutant MUST appear in neither the surviving mutants nor any test's kills

And the test selected only for that mutant MUST be listed as an unapplied-coverage test and MUST NOT be listed as a redundancy candidate

## Scenario: a kill-matrix run in which no mutant applies exits non-zero

Given a fixture package where every generated mutant fails to apply

When the kill-matrix engine runs over it

Then the run MUST exit non-zero with a finding naming the empty applied set

And it MUST NOT write a report that reads as a clean result

## Scenario: an unchanged package is not re-tested on a second kill-matrix run

Given a kill-matrix run over a fixture package that wrote its report and result cache

When the engine runs again over an identical tree, configuration, dependency set and engine version with that cache

Then the second run MUST re-test no mutant

And its report MUST equal the first run's report in every matrix-content field

And the report MUST state that the run was incremental and reused every mutant

## Scenario: a changed function's mutants are re-tested on an incremental run

Given a kill-matrix run over a fixture package that wrote its report and result cache

And one function of the package then changes its behaviour

When the engine runs over the package again with that cache

Then it MUST re-test every mutant located in that function

## Scenario: a change to a data file a test reads re-tests the mutants that test covers

Given a kill-matrix run over a fixture package that wrote its report and result cache, in which test T1 reads a data file and kills mutant M1

And that data file then changes so that T1 no longer fails against M1

When the engine runs over the package again with that cache

Then M1 MUST be re-tested

And the report MUST NOT list T1 as killing M1

## Scenario: a cached killer that is no longer a test is dropped and its mutant re-tested

Given a kill-matrix run over a fixture package that wrote its report and result cache, in which test T1 kills mutant M1

And T1 is then deleted from the suite

When the engine runs over the package again with that cache

Then T1 MUST NOT appear as a killer of M1 or of any other mutant

And M1 MUST be re-tested

## Scenario: a kill-matrix run reports newly redundant tests since the previous report

Given a previous kill-matrix report in which test T1 kills only mutant M1 and is M1's only killer

And a new test T2 that kills M1 and nothing else is then added

When the engine runs again with that previous report's path

Then its what-changed summary MUST list T1 as a newly redundant candidate, marked changed

And it MUST list T2 as a newly redundant candidate, marked new

## Scenario: a kill-matrix run reports newly surviving mutants since the previous report

Given a previous kill-matrix report in which mutant M1 is killed only by test T1

And T1 is then changed so that it no longer fails against M1

And a new function with a mutant M2 that no test kills is then added

When the engine runs again with that previous report's path

Then its what-changed summary MUST list M1 as a newly surviving mutant, marked changed

And it MUST list M2 as a newly surviving mutant, marked new

## Scenario: a surviving mutant whose function changed is flagged in the what-changed summary

Given a previous kill-matrix report that carries a function digest for mutant M1

And M1's function then changes so that M1 survives

When the engine runs again with that previous report's path

Then its what-changed summary MUST list M1 as a newly surviving mutant marked 'function changed'

## Scenario: a scheduled kill-matrix run writes its report without gating anything

Given an adopting repository with a scheduled kill-matrix job and a retained report from its previous scheduled run

When the schedule fires

Then the job MUST write a fresh kill-matrix report and a what-changed summary against the previous run's report

And the job MUST NOT be a required status check on any branch

And when the job is a CI workflow, its only triggers MUST be a schedule and manual dispatch

## Scenario: a warn-default finding whose lever CI arms fails a just check run that sets no lever

```gherkin
Given a tree carrying a finding of a warn-default check whose severity lever the CI workflow arms
And an environment that sets no LIVESPEC_FAIL_IF_* variable
When just check runs on that tree on a developer host, in a delegated gate Job, or in a factory sandbox
Then the run MUST fail
And it MUST name the same check and the same failure_mode that the CI job reports for that tree
```

## Scenario: a lever armed by CI but missing from the committed lever source fails the parity check

```gherkin
Given the CI workflow arms a LIVESPEC_FAIL_IF_* lever
And the committed lever source does not name that lever
When just check runs
Then the lever parity check MUST fail
And its finding MUST name that lever
```

## Scenario: a coverage target that fails on failing tests is reported as failing tests in the tail digest

```gherkin
Given a tree on which three tests fail when check-per-file-coverage runs the suite
When just check runs on that tree
Then the tail failure-mode digest MUST report check-per-file-coverage with failure_mode failing_tests
And it MUST name the node id of each of the three failing tests
And it MUST NOT report that target as having failed without a structured failure_mode
```

## Scenario: a CI coverage consumer with no usable receipt fails by name and starts no test run

Given the GitHub Actions coverage consumer is running
And the receipt is missing, or its data digest or tree digest does not match

When `scripts/just/check-coverage.sh` runs

Then it MUST exit non-zero with a message naming the cause
And it MUST NOT start a pytest process

## Scenario: a CI coverage consumer with a matching receipt judges the producer's data

Given the GitHub Actions coverage consumer is running
And the receipt matches the downloaded data and the checkout

When `scripts/just/check-coverage.sh` runs

Then it MUST read the producer's data without starting a pytest process
And it MUST exit zero at a 100 percent total and non-zero below it

## Scenario: a local coverage run with no reusable data still measures

Given `just check-coverage` runs outside GitHub Actions
And no reusable coverage data is present

When it runs

Then it MUST run and measure the clean suite

## Scenario: a commit that changes only a workflow runs the tests that read ci.yml

Given a commit stages a change under `.github/workflows/` or `scripts/just/` and no `.py` file
And a test that reads `.github/workflows/ci.yml` fails on the staged tree

When the pre-commit gate runs

Then it MUST run the test files that read `.github/workflows/ci.yml`
And it MUST refuse the commit

## Scenario: the coverage receipt is stamped over the final rewritten data

Given a coverage fixture that measures a source file deleted before report time

When the per-file coverage report runs over it

Then the stamped receipt MUST equal `scripts/just/coverage-reuse-id.sh` over the final rewritten `.coverage`

## Scenario: a coverage consumer that did not reuse reaches the maintainer

Given a fleet CI run whose mandatory coverage consumer job recorded an outcome other than `reused`

When the scheduled detector runs

Then it MUST raise a maintainer notification naming the repository, run, job and outcome within 30 minutes of that job's completion

## Scenario: a coverage consumer with no recorded outcome reaches the maintainer

Given a repository whose master CI runs of the last 24 hours include a mandatory coverage consumer job with no recorded reuse outcome

When the scheduled detector runs

Then it MUST raise a maintainer notification naming the repository and the job

## Scenario: a CI duration step change reaches the maintainer, and a runner-lane move does not

Given a fleet CI job whose 90th-percentile duration over the last 24 hours exceeds its 90th-percentile duration over the preceding 7 days by more than a factor of 2 and by more than 5 minutes, for the same job name and runner label

When the scheduled detector runs

Then it MUST raise a maintainer notification naming the job and both figures
And a job whose duration changed only because its runner label changed MUST NOT raise one

## Scenario: a stale detector reaches the maintainer

Given the detector's last successful run is older than twice its schedule interval

When staleness is evaluated

Then a maintainer notification MUST name the stale detector

## Scenario: a workflow declaring two container images fails its own CI

Given a pull request whose merge with the default branch makes `.github/workflows/ci.yml` declare two distinct job `container:` images

When its CI runs

Then the check MUST fail, naming each distinct image and its line
And the required all-green aggregate job MUST fail

## Scenario: a workflow declaring one container image passes

Given every job `container:` image in `.github/workflows/ci.yml` is the same reference

When the check runs

Then it MUST pass

## Scenario: a workflow GitHub cannot parse is refused at every gate

Given a `.github/workflows/*.yml` file that actionlint reports as unparseable

When it is committed, pushed, or carried by a pull request

Then the pre-commit gate MUST refuse the commit, naming the file, the line and the syntax-check message
And the pre-push gate MUST refuse the push, naming the file and the line
And a gating CI job MUST fail, naming the file and the line

## Scenario: a new runner release opens one bump across every scale set

Given a newer actions/runner release than the pinned version is published

When the pin-freshness surface runs

Then it MUST open one pull request moving every scale-set values file's runner image, and, where the file carries them, its container-hook path and preseeded-externals version, together

## Scenario: an aged runner pin raises a trigger

Given the pinned actions/runner version has been superseded for longer than 14 days

When the fleet trigger evaluates

Then it MUST fire naming the pinned version, the newest release and the age

## Scenario: two scale sets pinning different runner versions fail the check

Given two values files in `ci-runner/k3s/phase2/arc` or `ci-runner/k3s/arc` pin different actions/runner versions

When `just check` runs

Then it MUST fail

## Scenario: a run of a high-band work item on an opted-in lane is admitted ahead of earlier pending normal runs

Given `CI_PRIORITY_RECORD` bands work item W `high`

And the repository's pull-request lane sets `CI_RUNNER_LABELS_PRIORITY` and is at its churn-slot quota with normal workloads pending

When a pull request whose head branch names W starts its CI run

Then its gating jobs MUST run on the lane's priority runner set

And each of their pending workloads MUST be admitted before every earlier-created pending normal workload in that ClusterQueue

And admitting them MUST NOT evict any running workload

## Scenario: a run naming no high-band item keeps the lane's existing routing

Given `CI_PRIORITY_RECORD` names work item V `medium` and does not name work item U

When a pull request whose head branch names V, and another whose head branch names U, start their CI runs

Then both runs' gating jobs MUST run on the lane's existing routing

And a high-band run on a lane that does not set `CI_RUNNER_LABELS_PRIORITY` MUST also run on the lane's existing routing

## Scenario: a failed route job or an unusable record leaves gating jobs on their existing routing

Given `CI_PRIORITY_RECORD` is missing, does not parse, or carries a `generated_at` more than 72 hours old, or the route job fails

When a pull request starts its CI run

Then its gating jobs MUST run on the lane's existing routing and reach their own outcome

And the route job's summary MUST state why no priority was applied, when the route job ran

## Scenario: a master push carrying a high-band work item's commit runs on the master lane's priority set

Given `CI_PRIORITY_RECORD` bands work item W `high`

And the repository sets `CI_RUNNER_LABELS_MASTER_PRIORITY`

When a push to master carries a commit whose subject names W

Then the push run's gating jobs MUST run on the master lane's priority runner set

And a push whose commit subjects name no high-band item MUST run on the master lane's existing routing

## Scenario: the CI priority producer is idempotent and its dry-run writes nothing

Given the maintainer radar and the ledger are unchanged between two producer runs

When the producer runs twice, and then runs once with its dry-run flag

Then every fleet repository's `CI_PRIORITY_RECORD` after the second run MUST be byte-identical to its value after the first

And the dry-run MUST print each repository's value and MUST leave every `CI_PRIORITY_RECORD` unchanged

## Scenario: the range replay refuses a suite-green commit whose added tests fail on its parent

Given a commit that changes a product `.py` file, adds a test that fails when run against the commit's parent tree, and carries `TDD-Suite-Green-*` trailers but no `TDD-Red-*` trailers

When `check-red-green-replay` validates a range containing that commit

Then the check MUST fail

And its failure MUST name the commit and the test that fails on the parent

Given a commit that changes a product `.py` file, adds characterization tests that pass on its parent tree, and carries `TDD-Suite-Green-*` trailers with a `TDD-Suite-Green-Parent-Replay` trailer

When `check-red-green-replay` validates a range containing that commit

Then the check MUST pass that commit

## Scenario: a wall time that rounds up into the next unit is shown in that unit

Given the check aggregate has finished targets whose wall times are 59.96 s and 3599.6 s
When it writes the per-target wall-time table
Then the 59.96 s target shows as `1m 00s`, not `60.0s`
And the 3599.6 s target shows as `1h 00m 00s`, not `59m 60s`
And the `::: just <target>` lines and the structured `wall_s` field still carry raw seconds.

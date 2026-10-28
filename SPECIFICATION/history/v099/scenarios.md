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

And `release-please` opens a corresponding release PR on merge that cuts the next MINOR version

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

## Scenario: a stale warm-cache generation fires the trigger

Given the populator has not published a generation for longer than twice its schedule interval

When the host's liveness path emits the generation-age gauge

Then the stale-generation value trigger MUST fire with a runbook naming the populator

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

When the `factory` namespace's pod count stays at or above 90 percent of `factory-runs`' hard value for 15 minutes and a gate ClusterQueue has pending workloads with its CPU usage equal to its nominal quota

Then the fleet observability surface MUST show `factory-runs` used against hard per resource attributed by `k8s.namespace.name`

And that queue's pending count, admitted count and per-flavor CPU usage against nominal quota MUST be readable by queue name

And the factory ResourceQuota trigger MUST fire

## Scenario: an unready API server or a failing datastore fires its trigger

Given the API server readiness probe and the datastore gauges were converged by `ansible/ci-pool.yml`

When the API server's `etcd` readiness check fails for 3 consecutive minutes

Then the fleet observability surface MUST show the failing check by name with the probe's latency

And the API-server-unready trigger and the datastore trigger MUST both fire

## Scenario: a silent cluster-state emitter fires its dead-man

Given the cluster-state emitter has been reporting pod phase rows

When it reports none for 20 minutes

Then its dead-man trigger MUST fire while the pool nodes' dead-man triggers stay quiet

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

## Scenario: an opted-in push from a host that cannot read the gates kubeconfig gates locally

Given a consumer repository whose `[tool.livespec_dev_tooling]` table sets `delegated_gate = true`

And a pushing host where the pushing user cannot read the gates kubeconfig

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

# Independent incident observer

`incident_observer_endpoint.observer_endpoint` is a WSGI callback for individual
GitHub `workflow_job` completion events. It verifies the HMAC of the raw request
before reading the controller store. An authenticated first failing required leaf
can call recovery while the original workflow and its other jobs remain running.
It does not call a workflow-completion API, cancel CI, rerun jobs, classify the
failure or wait for a green revert PR.

The endpoint cannot register an incident from a request, label or environment
variable. Before merge, the independent host calls `arm_before_merge` with
`CurrentAuthorityReader` and its separately provisioned released-controller
allowlist. The durable arm binds the exact PR/base/head, incident generation,
operation, owner, original receipt bytes and complete required-leaf universe.
`observer_arm_admitted` checks that protected arm's id, PR/base/head and receipt
digest at the merge entrance. It refuses a consumed arm. No future master SHA or
CI run is invented before the merge, and a historical receipt cannot authorize
admission. The controller revision must differ from the candidate revision.

After merge, `bind_after_merge` retains the same canonical grant and uses
`MergedRunVerifier` to authenticate the merged PR/head, landed terminal SHA and
the exact normal push/master workflow run through independently provisioned
forge access. This fulfillment does not call the canonical tenant reader again,
so an already armed observer can bind during a tenant or wrapper outage.
Forge reads use the package's budgeted `gh_read` transport and the independent
host's provisioned credential, with a ten-second bound per read; no tenant
credential wrapper is inserted into this recovery boundary.
`admit_observer` remains a low-level standalone exact-master binding for an
already existing master run; it is not pre-merge readiness evidence and cannot
replace an arm's authenticated post-merge binding.

The controller's directory must live outside candidate checkouts, the tenant,
credential projection, factory and gates namespaces. The controller secret and
recovery principal must also be independently provisioned. Its private files are
cached immutable authority and effect receipts, not another lifecycle ledger.
They do not derive authorization by parsing arbitrary JSON supplied by an operator
or request.

Every repository mutation shares one OS-backed lock. An immutable recovery intent
is fsynced before the effect, and its registered generation is checked again
immediately before recovery. Duplicate delivery of another failing leaf shares
the same action id. An unknown outcome remains pending across process restarts;
it cannot issue another effect or admit a replacement generation until an operator
clears or retries it through the authenticated `POST /reconcile`
(`incident-observer-service.md`). The recovery
adapter must use that exact action id for the forge effect and its lookup.
Its `RecoveryIntent` carries the original typed `ObserverArm` when admission
used that protocol. The recovery callback already holds the repository lock
and must not acquire it again. The complete landed multicommit change and its
inverse must still be resolved at the authenticated recovery boundary; the
terminal merged SHA alone is not a rollback unit.

`reconcile_action_receipt`, the core of `POST /reconcile`, reads the exact external
effect receipt after a timeout and publishes it with the original authority bytes when the canonical tenant
returns. A newer registration never rebinds an older action's receipt to a newer
attempt. A completed reconciliation is retained to avoid duplicate publication.
Corrupt or inaccessible controller state fails rather than selecting normal mode
or starting with an empty fence.

The ordinary reconciler must ask the controller before its existing rerun,
classification, revert or fix-forward action. One owner rule, shared by
`route_ordinary_action` (the exact head/run form for in-process callers) and
`route_reconciler_window` (the reconciler's form), answers `incident-owned` for:

- an unbound pre-merge arm;
- a recovery action whose outcome is still unknown (`pending`), until
  `POST /reconcile` resolves it;
- the registered incident commit: its exact head SHA and run id, or, for the
  reconciler, that commit anywhere in the pass's window.

Anything else runs the existing policy under the same repository lock, and the
answer carries the controller's receipt for the one step it lets run. A fence
still held after ten seconds is the observer acting, so the reconciler's
question is answered `incident-owned` instead of waiting.

A reconciler pass does not act on one run. It reruns the newest failing run,
reverts the culprit at the bottom of the red episode and releases or closes a
revert, so its question covers every commit the pass can touch: the head back
to the newest green commit, the commit of the run it would rerun, and the
culprit it would revert (livespec-dev-tooling-ariayn, review finding F2 on
livespec-dev-tooling#3915).

The reconciler runs on a GitHub-hosted runner, far from the controller's
protected state, so it asks over the authenticated query route
`POST /ordinary-action` with the read-only query credential. The request is
exactly `{"repository", "action", "window_shas"}`, where `action` is the
reconciler step kind; the reply is exactly
`{"schema": 1, "status", "reason", "receipt", "query"}`. The workflow-side
transport is `python3 -m livespec_dev_tooling.master_health_observer
--repository R --state state.json --runs runs.json --step step.json`. It lives
outside `cross_repo/master_health_*` because those decision modules are kept
network-free by test. It prints one JSON object:

- `incident-owned` (exit 0): rerun, classification and revert are left to the
  observer.
- `ordinary` (exit 0): the existing policy runs unchanged. A step that takes no
  action, and a repository with no observer, answer `ordinary` without asking.
- No readable answer in a repository that has an observer (exit 1): the cause
  is named on stderr, nothing is printed, and no action is taken in that pass.

**Which repositories have an observer is committed configuration.**
`master_health_observer.OBSERVED_REPOSITORIES` lists them, and a test keeps it
equal to the observer role's `incident_observer_repository`. A repository in
that set whose `LIVESPEC_INCIDENT_OBSERVER_URL` reads empty fails closed: a
variable that is not mapped through, or that a typo empties, must not read as
"no observer" (review finding F4).

**The answer is a snapshot, not a lease.** It is taken under the repository
fence and read immediately before the one side effect, not before the gather.
A lease the reconciler held across its step would have to delay arming or
recovery, and the credential asking is the read-only hosted query credential;
giving it the power to hold back an incident's arm or recovery would open a
denial of the recovery path. Two paths make a master commit incident-owned,
and the remaining seconds differ for each (review finding F3):

- Through the pre-merge arm, the normal incident path. The arm is made before
  the merge, so the answer already reports it as `incident-owned`, and the merge
  waits on the incident PR's own CI. That takes far longer than the seconds
  between the answer and the step.
- Through `admit_observer`, which binds a registration to an EXISTING master
  commit and run with no arm. A registration it writes between the answer and
  the step is not seen by that step. It has no production caller today: the
  observer service exposes no route to it. A standalone admission also names a
  run that has already failed or passed, so the reconciler may already have
  acted on it before any admission. The race is one ordinary step taken seconds
  before the admission, and the reconciler's next pass asks again and sees the
  registration. Declining the lease still costs less than the denial it would
  open. If `admit_observer` gains a production caller, that caller must account
  for a reconciler step already in flight.

**Reachability is a precondition for installing the reconciler where an
observer runs.** The observer is served only on the tailnet, and the reconciler
runs on GitHub-hosted runners by design, because the self-hosted pool can be the
failure it heals. A hosted runner that cannot reach the observer gets no answer,
so every pass with an action in an observed repository exits 1: fail closed,
never open. Today no observed repository runs the reconciler:
livespec-dev-tooling, the only observed repository, carries no
`master-health-reconcile.yml` shim, and `livespec`, which does, has no observer.
Before the shim is installed in an observed repository, a hosted runner must be
proven to reach `POST /ordinary-action` (review finding F5). `wire-fleet-member`
enforces that order. It refuses to install the shim into a repository in
`OBSERVED_REPOSITORIES` until the committed opt-in
`master_health_observer.HOSTED_REACHABILITY_PROOFS` maps that repository to the
URL of a GitHub-hosted Actions run that reached the route
(`https://github.com/<owner>/<repo>/actions/runs/<id>`), and names the missing
proof as a finding. A member with no observer is installed as before. Recording
the proof and arming livespec-dev-tooling is livespec-dev-tooling-jpfdcx.

**The hosted route is public, through the observer's Funnel.** The maintainer
ruled the route on livespec-dev-tooling-jpfdcx (option A, 2026-11-10): "If it
is not adding any security concerns that we don't already have, then it's good
enough for now." The observer role publishes `POST /ordinary-action` through
the same path-scoped Tailscale Funnel that already makes `POST /callback`
public, at `https://vps.perch-rudd.ts.net:10000/ordinary-action`. The role
declares its public paths as a list (`incident_observer_funnel_paths`). Each
entry is an exact path proxied to the same path on production's loopback port,
never `/`. An apply refuses when a publish leaves a declared path unpublished,
and whenever the funnel port publishes a path the list does not name. A scratch
instance publishes nothing (`ansible/roles/incident_observer/README.md`). Every
other route stays tailnet-only: the other query routes (`/current`, `/admitted`,
`/provenance` and the rest), the CI identity routes and the control routes. The route is read-only: the query token is checked before
the body is read, a missing or wrong token gets 403, and the route writes
nothing. It takes the repository lock only to read.

The reconciler reads the public URL from its own repository variable,
`LIVESPEC_INCIDENT_OBSERVER_PUBLIC_URL`. When that variable is set, the
reusable reconciler workflow passes it as the observer URL and passes NO
connect-address override, so the runner dials the public name. When it is
unset, the reconciler reads `LIVESPEC_INCIDENT_OBSERVER_URL` and
`LIVESPEC_INCIDENT_OBSERVER_CONNECT_ADDR` exactly as before. The incident CI
job on the k3s runners keeps those two variables unchanged: it reaches the
tailnet port 8765 through the connect address (decision C3 under
livespec-dev-tooling-ws2idp), and emptying them would break it.

Accepted risks, named in the ruling:

- **An occasional failed read through the Funnel.** The reconciler then fails
  closed. It takes no rerun, classification or revert action in that pass, and
  the five-minute schedule asks again.
- **The observer is single-threaded (`wsgiref`) and now has two public
  paths.** A flood of requests to `/ordinary-action` can hold it busy exactly
  as a flood to `/callback` already can. Every such request is refused at the
  token check before its body is read, but the listener serves one request at
  a time.

Follow-up owed: isolate the observer on its own host, so a flood of its public
paths cannot contend with the dev host's other services.

This source slice supplies controlled callback and action adapters. It does not
activate a production observer. Activation and child closure still require:

- The released canonical `incident_authority.py read-current` adapter, including
  exact repository/item/attempt/phase/operation/generation/owner validation and an
  immutable receipt. Its schema-1 `result.attempt` is encoded as sorted compact
  JSON to obtain the exact authority bytes; `authorizes_current_effects` must be
  true, and history results cannot admit. Pre-merge arms bind the canonical
  PR/base/head; standalone existing-master admission additionally requires the
  registered master SHA in the authorized landed commit set. This reader does
  not select CI run ids: the independent released controller must also verify
  exact PR/run/SHA association through its authenticated forge boundary.
  Current incident identity alone cannot authorize an arbitrary run. Reader
  unavailability refuses new admission but does not revoke a retained arm's
  fulfillment grant.
- A normally installed independent released controller, GitHub webhook delivery,
  protected directory, host authentication and narrow recovery capability.
- Wiring canonical correction/ownership transitions to advance the controller
  fence **before** any new attempt can perform effects. A pending unknown effect
  must first be resolved by its exact receipt. (The ordinary reconciler's side of
  the shared action lock is described above.)
- Released-build rollout and controlled end-to-end proof, including tenant and
  credential-wrapper outages. Local fixture authority is not live authorization,
  a factory record or proof of installed fleet behavior.

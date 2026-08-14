# CI runner failover

`reusable-ci-runner-router.yml` chooses exactly one execution lane for ordinary
CI before any job that could use the local pool is created. It always runs its
selector on `ubuntu-latest`, then emits either `['ubuntu-latest']` or the
caller-supplied self-hosted label JSON. It never emits a mixed label array:
GitHub matches every label in an array and does not retry an unmatched
self-hosted job on a hosted runner.

## Normal operation

Callers supply their local labels in source control, rather than treating a
mutable repository variable as the routing decision. In `auto` mode the router
uses the read-only Actions runner API and selects local only after two bounded
observations, separated by 30 seconds, each find an online, idle runner
carrying every required label. An API error, no matching runner, or a recovery
flap selects `ubuntu-latest` immediately. The job summary records the lane,
safe reason, and both probe results, including how long the first probe
waited through saturation; automatic mode makes at most two API list requests
plus one per saturation poll, a deliberate rate/cost cap.

## Outage vs. saturation

The first probe distinguishes two different kinds of "no idle runner right
now," because they call for different responses:

- **Outage** — zero runners online at all that carry the required labels
  (`online_matching == 0`), or an API/parse error. This routes to hosted
  **immediately**, with no waiting: the pool is unavailable, and waiting
  cannot help.
- **Saturation** — at least one matching runner is online, but every one of
  them is currently busy (`online_matching > 0`, `idle_matching == 0`). This
  is routine, expected fleet behavior, not an incident: the pool is healthy,
  just fully booked. The probe polls on `saturation-poll-interval-seconds`
  (default 15s) for up to `saturation-grace-seconds` — a `workflow_call`
  input on the reusable router, **default 300 seconds (5 minutes)** — before
  giving up. As soon as any poll observes an idle matching runner, the job
  routes local immediately; it never waits out the rest of the window.

The 5-minute default is deliberate, not arbitrary. Some repos in the fleet —
`homelab` is the motivating example — have no warm build cache (e.g. no Nix
binary cache) on GitHub-hosted runners. A cache-cold hosted job on such a repo
can run an order of magnitude slower than a warmed local runner would. In
that situation, queuing for a few minutes of local capacity to free up is
cheaper, in both wall-clock time and hosted-runner spend, than failing over
immediately. Callers that don't share this cache asymmetry can override
`saturation-grace-seconds` down (including to `0`, which reproduces the
pre-grace-window behavior of failing over the instant no runner is idle) via
the `workflow_call` input.

If the grace window elapses while still saturated, the job routes hosted with
a `saturated-timeout` reason — distinct from the outage reasons
(`no-online-matching-runner`, `runner-api-error`) — so the job summary and any
downstream alerting can tell "the pool was down" apart from "the pool was
just busy and stayed busy."

The existing two-probe/30-second recovery hysteresis is unchanged and applies
only once the first probe has already reported healthy (an idle runner was
observed, whether on the first read or after waiting through saturation): the
router still confirms that healthy state is stable before trusting it.

`CI_RUNNER_FAILOVER_MODE` is the caller's operational override:

- `auto` is the default and is the only normal mode.
- `hosted` keeps ordinary CI on GitHub-hosted capacity during maintenance or
  incident response.
- `local` is a trusted-event break-glass override. It bypasses health probing
  and can therefore queue if an operator uses it while the pool is down.

Fork-originated pull requests are always routed hosted, even with `local`; the
router never lets a repository variable override that trust boundary. Privileged
golden-master workflows do not call this reusable workflow and remain on their
dedicated gate lane.

## Failure and recovery semantics

The selector only controls jobs created after it completes. If the local pool
goes down after the selector chooses local, an already **queued** job remains
queued because GitHub cannot migrate it to another `runs-on` target. If an
**in-progress** local job loses its runner, GitHub reports that job failed or
cancelled. Re-run the workflow (or the failed jobs): its new hosted selector
will observe the outage and route the retry to GitHub-hosted capacity.

When the pool returns, the next normal CI run observes two healthy samples and
returns to local automatically. Operators should leave mode at `hosted` until
the pool's own recovery proof is complete when an incident requires a longer
cooldown; switching the override back to `auto` restores automatic recovery.

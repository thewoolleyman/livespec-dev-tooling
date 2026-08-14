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
safe reason, and both probe results; automatic mode makes at most two API list
requests, a deliberate rate/cost cap.

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

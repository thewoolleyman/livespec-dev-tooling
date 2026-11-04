# A factory restart cancels its runs; it never waits for them

A Fabro factory run is restartable. When a server restart, an engine upgrade or
a chain step needs a factory with zero active runs, CANCEL the live runs, do the
step, and re-dispatch every cancelled item at once — or route it to another
factory. Never hold the fleet cap at 0 waiting for runs to end naturally.

## The maintainer direction (2026-10-24)

Given at about 00:4xZ, relayed verbatim by the coordinator
`gitops-fleet-capacity-monitoring`:

> You're blocking the whole fucking upgrade because you don't want to kill a
> run, which can easily be restarted immediately after the restart or even on
> another app.

## What it cost

The fleet cap sat at 0 from 2026-10-23 22:5xZ to 2026-10-24 00:4xZ — about
1 h 50 min — while gmktec's restart onto Kubernetes v0.4.1 waited for its
active runs to finish on their own. The account carrying that work was
under-used for the whole window, so the wait bought nothing: every run it
protected could have been re-dispatched within minutes of the restart.

## The guard means "cancel to idle", not "wait for idle"

The `fabro_server` role refuses to restart an instance that is carrying runs
(see `ansible/roles/fabro_server/HOST_VARS.md`). That refusal is honoured,
never bypassed: do not blind its probe, skip it, or restart by hand around it.
It tells you WHAT to make true before the restart — no active run — and the way
to make it true is to cancel the runs, not to wait for them.

## How to cancel a run

No Fabro client has a cancel command: neither the 0.254 client nor the 0.382
petri carrier client lists a `cancel` subcommand. The cancel is the SERVER's
own endpoint:

```text
POST /api/v1/runs/{id}/cancel     (bearer token)
```

It cancels a pending, runnable or running run and answers 409 for a run that
has already finished or been cancelled. Measured 2026-10-24: the endpoint is in
the published OpenAPI of both the vps server (0.254) and the gmktec server.

`fabro rm --force` is NOT a cancel. It deletes the run's record, and with it
everything reachable only through `inspect`, `dump` and `attach`. Removing a run
is governed separately — only a dead run, and only after a read-back-verified
export (livespec-orchestrator-beads-fabro `AGENTS.md`, "Export, then reap").

## The sequence

1. List the instance's active runs: `fabro ps --server <instance>`.
2. Record each run's work-item id; you will re-dispatch exactly that set.
3. Read each run's CURRENT STAGE before cancelling anything. A run in
   `publish_draft` or `pr_refresh` has passed janitor and is pushing or
   refreshing its green commit; never cancel it blind. Either let it finish
   its publish step, or first preserve its green commit to a
   `needs-human/<item>-<date>` ref on the target repository's origin, then
   cancel it.
4. Cancel each run through `POST /api/v1/runs/{id}/cancel`.
5. Confirm `fabro ps --server <instance>` shows none active.
6. Do the step — the restart, the upgrade, the chain step — through its normal
   path, with the role's restart flag where it applies. Keep the window
   between the cancel and the re-dispatch short; see "Keep the restart play
   short" below.
7. On a Kubernetes-backed instance, reap the cancelled runs' sandbox pods
   BEFORE you re-dispatch anything. Run the next step after every
   cancel-to-idle restart on gmktec, of either instance.
8. Re-dispatch every cancelled item at once, or route it to another factory.
   Read each item's ledger state before re-dispatching it.

What it cost: on 2026-11-04 the main gmktec instance (`:32276`) was cancelled
to idle at 09:56:18–09:56:35Z for the c39bdbd engine restart (plan
`fabro-currency`, epic `bd-ib-6tcjfx`, session `claude:fabro-currency`).
Thirteen runs were cancelled without reading their stages. One of them,
`bd-ib-uq2ocd` run `01M6JSNVH32S8`, had passed janitor and was mid-push in
`publish_draft`. Its green commit was lost: the run record shows no diff, and
its sandbox pod was gone after the cancel. The ruling to read stages first is
`legacy-coordinator-agent`'s, given the same day.

## Keep the restart play short

The restart play converges far more than the restart. In the same 2026-11-04
window,

```text
just ansible-apply ansible/fabro-hosts.yml --limit gmktec-xubuntu \
  -e '{"fabro_server_target_units": ["fabro-server"]}' \
  -e fabro_server_restart_allowed=true
```

converged every gmktec role in order before the `fabro_server` restart handler
fired, so the factory sat cancelled but not restarted for many minutes.
`fabro_server_target_units` narrows only the `fabro_server` loop, not the roles
ahead of it.

There is no tag to narrow the play to the restart: `fabro_server` is reached
through an untagged `include_role` task in `ansible/fabro-hosts.yml`, and the
role itself carries no tags (checked 2026-11-04). Until one exists, start the
restart play BEFORE cancelling, and cancel when its output reaches the last
role ahead of the include (`fabro_server_cpu_weight`). The role's busy probe
refuses the restart if any run is still active when it fires, so the cancel
must be confirmed (step 5) before the play reaches the include. The missing tag
is a gap: a tag on that include task would let `--tags` run the restart alone.

## Reap the abandoned sandbox pods before re-dispatching

A restart abandons the cancelled runs' in-flight sandboxes. On the Kubernetes
provider each one is a pod that keeps its slot of the namespace's
`ResourceQuota`, so the re-dispatched runs meet a quota the dead pods already
hold. The engine defect behind this is being filed under `bd-ib-nmuyjc` by the
`kubernetes-sandbox-backend` session. Coordinator standing rule, 2026-10-24:

1. On the factory host, as the instance's own account (the plugin reads its
   provider profile from that account's HOME), list the provider's sandboxes and
   delete every one whose run is not live in `fabro ps --server <instance>`:

   ```text
   lithos-sandbox --provider kubernetes sandbox delete <sandbox-id>
   ```

   `lithos-sandbox` is installed in `/usr/local/bin` by the
   `sandbox_driver_kubernetes` role. Use the driver's own command and do not
   delete pods with `kubectl`, which would leave the provider's records behind.
2. Read the namespace quota's `used` figure back and confirm it equals the live
   run count × 4 cpu.

What it cost: the `#2803` restart left two such pods (the `rpw6` and `wt7fv4`
runs). They held the fleet namespace's quota, and the next dispatch,
`livespec-dev-tooling-c62xtb`, was refused with a 403 until they were reaped.

# Handoff — sandbox-image-tmux

**Ledger anchor:** epic livespec-dev-tooling-fhv1

## Your next action

**Dispatch `livespec-dev-tooling-myx7` to the factory.** It is `ready`,
tiered `factory`, and carries a full design and acceptance.

```bash
cd /data/projects/livespec-dev-tooling
/livespec-orchestrator-beads-fabro:drive --action impl:livespec-dev-tooling-myx7
```

Or let the Dispatcher drain it — it is `ready`, so it will be picked up.

**Do NOT implement it in this session.** Ready, factory-safe work is
built factory-side under the janitor gate; the in-session Red→Green
driver is not the route for this item.

Read `livespec-dev-tooling-myx7`'s own design field before dispatching
— it carries the full implementation contract, including two things
that are wrong by default (§Traps below).

## Read-first chain

1. This file.
2. `bd show livespec-dev-tooling-myx7` — the doing record: ACCEPTED
   ruling, autonomy tier, design, acceptance.
3. `plan/sandbox-image-tmux/research/why-this-shape.md` — why the
   change has this shape, what was verified, and the findings.
4. `plan/sandbox-image-tmux/supervisor-handoff.md` — the supervision
   charter (Control-Plane; not a thread handoff).

```bash
cd /data/projects/livespec-dev-tooling
/usr/local/bin/with-livespec-env.sh -- bd show livespec-dev-tooling-myx7
/usr/local/bin/with-livespec-env.sh -- bd show livespec-dev-tooling-fhv1
```

## What this thread is

Add `tmux` to `docker/fabro-sandbox/base/Dockerfile`'s apt install and
release dev-tooling, so `livespec-overseer` can bump its pin.

Its slices `overseer-ykneip` (S1) and `overseer-4do7jx` (S2) drive REAL
tmux on a private socket to prove HALT-first preconditions can FAIL.
Both carry a `sibling_work_item` dependency on
`livespec-dev-tooling-myx7`, so they are gated and cannot drain until
this lands. They are factory-tier, so they get dispatched INTO that
sandbox — which is why the fix belongs in the shared image and not in
the consumer's CI.

Status is READ from the ledger, never stored here. Compose it with
`bd show` / the `list-work-items` and `next` operations.

## Traps — both are wrong by default

1. **`chore(...)` cuts NO release.** `release-please-config.json` hides
   `chore`/`build`/`ci`/`docs`/`test`/`style`, so only `feat:`/`fix:`
   bump. A `chore(docker):` merge publishes `base-sha-<short>` tags and
   stops: no `python-agent-v<X.Y.Z>` tag, so `livespec-overseer` has
   nothing to pin to while the change sits on master **looking done**.
   Use `fix(fabro-sandbox):`. Precedent `00c5d9f fix(ci):` added
   `libatomic1` to this exact apt line. This CONTRADICTS the plain
   reading of `AGENTS.md` §"Red-Green-Replay commit protocol"; precedent
   wins.
2. **Raw `git worktree add` yields a worktree that cannot commit or
   push.** The discipline pack is gitignored-and-materialized and is
   copied only by `worktree-lib.sh create`, so a raw-created worktree
   fails `check-primary-checkout-commit-refuse-hook-installed` with
   `worktree_pack_absent` — at commit/push time, after the work is done.
   Not `.py`-specific. Use `just worktree-create`, or `just
   install-worktree-pack` to repair. Filed as
   `livespec-dev-tooling-f7xs`; `AGENTS.md:83` still documents the raw
   command.

## Do not cite this as evidence

`check-plan-thread-epic-parity` is **dark**: it self-skips unless
`LIVESPEC_RUN_PLAN_EPIC_PARITY` and `BEADS_DOLT_PASSWORD` are both set,
and the lever appears nowhere in `.github/`, so it is unarmed in CI as
well as locally. Its green is not evidence of parity. An instance of the
class `livespec-dev-tooling-pk2x` exists to close.

## Ledger records this thread owns

| id | what | note |
|---|---|---|
| `livespec-dev-tooling-fhv1` | epic — the planning anchor | Planning anchor only; never restates the work. |
| `livespec-dev-tooling-myx7` | the DOING record | `ready`, tier `factory`. Single residence — `livespec-overseer` references this exact id. |
| `livespec-dev-tooling-f7xs` | the `AGENTS.md:83` worktree trap | Filed separately; deliberately NOT folded into the tmux changeset. |

`myx7` is linked to `fhv1` with `relates_to`, **not** `--parent`: this
store assigns dotted child ids at creation
(`livespec-dev-tooling-8o8e.1`), and a reparent that renamed `myx7`
would break the cross-repo gating that references it by name. `bd`
also refuses an epic→task dependency ("epics can only block other
epics, not tasks").

## Closing this thread

Close `fhv1` and `git mv plan/sandbox-image-tmux/
plan/archive/sandbox-image-tmux/` when: `myx7` is closed, dev-tooling
is released with tmux in the base image, and `livespec-overseer` has
bumped its pin. The pin bump is the CONSUMER's action in the consumer's
repo — it is not this repo's changeset, so confirm it against that repo
rather than assuming it followed.

## Repo conventions that bind here

`just worktree-create`, never raw `git worktree add`. `mise exec -- git`
so lefthook fires; never `--no-verify` — halt and report on hook
failure. Worktrees live under
`~/.worktrees/livespec-dev-tooling/<branch>`. Post-merge cleanup is
required: refresh the primary to `origin/master`, remove the worktree,
delete the branch, leave no orphans — and verify the change is upstream
with `git cherry`, since rebase-merge rewrites the sha and
`--is-ancestor` would mislead. Never touch another session's worktrees
or branches; several are live.

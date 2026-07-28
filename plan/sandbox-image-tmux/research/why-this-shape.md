# sandbox-image-tmux — why this shape

Opened at the maintainer's direction, routed from the `livespec-overseer`
repo. Research-only at this point: no handoff and no ledger epic anchor
yet, both deferred to an explicit maintainer ruling (§Decisions taken).

## The request

`livespec-dev-tooling-myx7` (P1, `backlog`) — add `tmux` to
`docker/fabro-sandbox/base/Dockerfile`'s apt install, release
dev-tooling, so `livespec-overseer` can bump its pin.

Routed IN from the `livespec-overseer` track (its plan thread
`plan/supervisor-prompt-quality/`, epic `overseer-byvxlp`). It is a
cross-track handoff, so this repo owns an accept-or-reject decision,
not merely an implementation. `myx7`'s own acceptance criteria say so:
"Rejection with a stated reason is an acceptable outcome."

## What was verified here, not inherited

The requesting track supplied evidence three ways. This thread re-ran
the load-bearing parts rather than adopting them.

1. **The apt install really is `libatomic1` only.** Read directly:
   `docker/fabro-sandbox/base/Dockerfile:59-63`. The `python` layer
   (`docker/fabro-sandbox/python/Dockerfile`) adds uv + CPython and no
   packages.

2. **tmux is absent, and the absence is a property of the image
   family.** `docker run` against three locally-present pinned tags:

   | tag | tmux | git |
   |---|---|---|
   | `python-v0.56.2` | ABSENT | PRESENT |
   | `python-v0.56.4` | ABSENT | PRESENT |
   | `python-agent-v0.56.6` | ABSENT | PRESENT |

   The requesting track's evidence covered the first two. This thread
   extended it to **`v0.56.6` (the current release) and to the `agent`
   variant** — the tag a *factory-dispatched* slice actually runs, and
   therefore the one that matters most for the consuming slices. `git
   PRESENT` on every row is the control: the negative is a real
   absence, not a broken entrypoint or an empty image.

3. **The consuming need is real.** `livespec-overseer` slices
   `overseer-ykneip` (S1) and `overseer-4do7jx` (S2) drive real tmux on
   a private socket to prove HALT-first preconditions can FAIL. Their
   maintainer rejected a tmux-behavior stub deliberately. Both already
   carry a `sibling_work_item` dependency on `myx7`, so they are gated
   and cannot drain until this lands.

## Why the base image rather than the consumer's CI

Adopted from the requesting track and endorsed: `ci.yml`'s own comment
states the container is the SAME tag the Fabro sandbox runs, and that
sameness exists to collapse green-in-CI / red-in-sandbox drift. The
consuming slices are factory-tier, so they get dispatched INTO that
sandbox. A CI-only `apt-get install` would make them green in CI and red
in the sandbox for an environmental reason — reintroducing exactly the
drift the shared image was factored to eliminate, in slices whose entire
subject is verifiers that mislead.

### The agent-leaf alternative, explicitly rejected

Distinct from the CI-only option and worth rejecting on the record
rather than passing over: tmux could go in the `agent` leaf
(`docker/fabro-sandbox/agent/Dockerfile`) instead of `base`. That would
confine the cost to the layer the dispatched slices actually run.

Rejected. CI pulls `python-*` / `python-rust-*`, **not** the agent leaf
(the layer tree comment in `.github/workflows/fabro-sandbox-image.yml`
is explicit that the agent payload is kept out of the CI path). Putting
tmux only in the leaf would mean CI lacks it while the sandbox has it —
recreating the CI-vs-sandbox divergence for tmux specifically, which is
the very property the base-layer argument rests on. Base is where every
consumer inherits it, so base is where it belongs.

## Cost, sized by this repo's own standard

The base Dockerfile weighs additions explicitly: its `libatomic1`
comment sizes a 10.5 kB library (50.2 kB installed) against the 176.9 MB
the `-scm` re-base saves, and the header comment states plainly what is
deliberately NOT in base. The tmux argument has to meet that bar —
measure the installed size (tmux pulls `libevent-core` and `libutempter`
on noble) and state it in the commit body, as `00c5d9f` did.

tmux has no daemon at rest and is not a compiler or dev-header re-add,
so it does not violate the `-scm` rationale. Blast radius is fleet-wide
but shallow: every consumer of base gains one package.

## The sequencing trap this thread found

`myx7` says "release dev-tooling so the pin can move." That step is not
automatic, and the obvious commit subject breaks it.

- `release-please-config.json` sets `release-type: python` and marks
  `chore`, `build`, `ci`, `docs`, `test`, `style` **hidden**. Only
  `feat:` and `fix:` produce a version bump.
- `AGENTS.md` §"Red-Green-Replay commit protocol" says changesets with
  no product `.py` — explicitly including config — "use `chore(...)` /
  `docs(...)`" subjects.
- A Dockerfile change carries no product `.py`, so the protocol's plain
  reading points at `chore(docker):`.
- **`chore(docker):` cuts no release.** The merge would publish
  `base-sha-<short>` per-commit tags and stop. No new
  `python-agent-v<X.Y.Z>` tag would exist, so `livespec-overseer` would
  have nothing to bump its pin *to* — the consumer stays blocked while
  the change sits merged on master, looking done.

**Resolution, from this repo's own precedent.** Dockerfile-only changes
here already ship under release-cutting subjects:

| commit | subject | change |
|---|---|---|
| `00c5d9f` | `fix(ci):` | re-based the chain onto `-scm`; **added `libatomic1` to this exact apt line** |
| `7339303` | `fix(fabro-sandbox):` | baked bubblewrap + codex-acp adapter |
| `a03be53` | `feat(dev-tooling):` | split the image into base/python/python-rust layers |

`00c5d9f` is the near-exact template: same file, same apt-install line,
same shape (one package added with a measured size justification),
shipped as `fix(ci):`. Its commit body also sets the verification bar —
it records that the whole five-image chain builds and that `just check`
passed.

## Publish mechanics (why the pin can move at all)

`.github/workflows/fabro-sandbox-image.yml` has three triggers:

- **PR** touching image paths → builds the whole tree to an ephemeral
  in-job `localhost:5000` registry, publishing nothing. This validates
  that every layer still builds, so the PR itself is the build gate.
- **push to master** → immutable per-commit `*-sha-<short>` tags.
- **release published** → immutable semver `*-v<X.Y.Z>` tags. Critically,
  "`paths` filters do not apply to release events, so EVERY release gets
  semver-tagged layer images," and release-please authenticates via the
  livespec App installation token so its releases **do** fire this event.

Consequence: once the change is on master under a release-cutting
subject, the next release republishes the full semver layer set with
tmux in it. No manual image step is required.

## State of `myx7` as filed

`myx7` is `status: backlog` with acceptance criteria but **no
`autonomy_tier` and no design/notes**. It is a *request record* routed
from another repo, not a ready slice, and cannot be drained by the
Dispatcher in this state.

This matters for any future handoff: the plan operation's
self-sufficiency gate requires a handoff whose next action names the
factory dispatch route (`drive --action impl:<id>` or a Dispatcher
drain). There is no such route to name until `myx7` is groomed to
`ready` with an explicit tier, or accepted and given a ready child.
Recording this so the gate is not failed by surprise later.

## What the deferred epic anchor does and does not cost

Measured rather than assumed, because deferring the anchor could have
stranded this thread in a failing state.

- **`check-plan-thread-anchor-declared`** scans `plan/*/handoff.md` and
  fails any active handoff that does not declare a concrete
  `**Ledger anchor:** epic <id>`. It is credential-free and "runs
  everywhere, including consumer CI" (`justfile:838-841`). It passes
  today only because this thread is **research-only with no
  `handoff.md`**. The coupling is hard: *a thread handoff cannot be
  authored until the epic anchor exists.* That is the real cost of the
  deferral, and it is a sequencing constraint, not a blocker.
- **`supervisor-handoff.md` is NOT affected.** The check's glob is
  `*/handoff.md` — the exact filename only
  (`plan_thread_anchor_declared.py:48`). A Control-Plane
  `supervisor-handoff.md` is not scanned and needs no ledger anchor,
  which `plan/rop-railway-enforcement/` confirms in practice: only its
  `handoff.md:3` carries the anchor line. So supervision artifacts can
  be authored against this thread now.
- **`check-plan-thread-epic-parity` is dark.** It self-skips unless
  `LIVESPEC_RUN_PLAN_EPIC_PARITY` **and** `BEADS_DOLT_PASSWORD` are set
  (`justfile:843-848`). Verified: the lever appears **nowhere** in
  `.github/`, so it is unarmed in CI as well as locally — its green is
  not evidence of parity. This is a concrete instance of the class epic
  `livespec-dev-tooling-pk2x` exists to close, and it is worth noting
  that it sits in exactly the area this thread is deferring a decision
  in. A verifier that cannot fail is the same defect as a precondition
  that cannot fail.

## Finding: AGENTS.md points at a worktree command that traps the reader

Reproduced and confirmed in this repo.

- `AGENTS.md:83` documents creating worktrees with raw
  `mise exec -- git -C <primary> worktree add -b <branch> ...`.
- The worktree-discipline pack (`dev-tooling/worktree-lib.sh`,
  `worktree.just`, `branch-protection.{sh,just}`) is
  **gitignored-and-materialized, never tracked** — `justfile:63-66`
  imports the two `.just` fragments with `import?` precisely because
  they are absent until `just install-worktree-pack` runs.
- `just worktree-create` routes to `worktree-lib.sh create`, which
  **copies the pack from the primary into the new worktree**
  (`worktree-lib.sh:124-136`, `source_dir="$primary/dev-tooling"` →
  `dest_dir="$dest/dev-tooling"`). Observed directly while creating
  this thread's own worktree: `worktree-lib provision-pack: installed
  worktree-discipline pack in .../dev-tooling`.
- Raw `git worktree add` copies nothing. The new worktree therefore has
  no pack, and `check-primary-checkout-commit-refuse-hook-installed`
  fails with `failure_mode: worktree_pack_absent`.
- It fires at **commit and push time — after the work is done.**

Corroborated independently by two other threads in this repo, which
each paid for it:

- `plan/rop-railway-enforcement/handoff.md:231-234` — "Run `just
  install-worktree-pack` in the new worktree BEFORE the first commit.
  It cost two failed commit attempts here."
- `plan/rop-railway-enforcement/supervisor-handoff.md:329-333` — same
  trap, same cost.

Two refinements over the initial framing of this finding:

1. **The trap is not `.py`-specific.** `red_green_replay` is the
   `.py`-gated ritual; `check-primary-checkout-commit-refuse-hook-installed`
   is a *separate* check that fires on any commit in a pack-less
   worktree. A docs- or Dockerfile-only changeset — including this
   thread's own — hits it too.
2. **`just worktree-create` is not the only remedy.** `just
   install-worktree-pack` inside a raw-created worktree is the
   documented standalone repair path (`justfile:118-123`).

This repo OWNS that pack, so its own guidance pointing at the raw
command is a live trap for anyone following it — including agents
booted with AGENTS.md as their instruction set. To be filed as its own
work item once ledger writes are approved; deliberately NOT folded into
the tmux changeset.

## Scope boundary

`livespec-dev-tooling-myx7` is the DOING record and lives here. The
requesting repo holds only a GATING handle. This thread must not create
a second record of the same obligation: any epic anchor is a *planning*
anchor, under which `myx7` links as the existing doing record rather
than being restated.

## Decisions taken

| decision | ruling | rationale |
|---|---|---|
| What lands at thread open | Research note via PR; **ledger epic anchor deferred** | Standing clause: nothing is filed in the ledger without maintainer approval. The plan operation permits a young research-only thread. |
| Image layer | **`base`**, as requested | Agent-leaf confinement would break CI-vs-sandbox sameness for tmux — see §agent-leaf alternative. |
| Commit subject for the tmux change | **`fix(fabro-sandbox):`**, and flag AGENTS.md | `chore(...)` cuts no release and would strand the consumer; `00c5d9f` is direct precedent. AGENTS.md's stated rule is incomplete for release-bearing config changes. |
| AGENTS.md worktree trap | Record here, **file separately** | Keeps the finding owned without entangling the tmux changeset. |

## Open questions

- Measured installed size of tmux + `libevent-core` + `libutempter` on
  `buildpack-deps:noble-scm`, to be stated in the commit body at the
  standard `00c5d9f` set.
- Whether `myx7` is groomed in place to a ready, tiered slice or
  accepted with a ready child created under it.
- Whether AGENTS.md's `chore(...)` rule should be amended to carve out
  release-bearing non-`.py` changes, or whether the release mechanics
  are better documented at the Dockerfile.

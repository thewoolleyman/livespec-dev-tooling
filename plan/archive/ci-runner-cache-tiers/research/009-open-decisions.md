# 009 — The six open decisions, written for a session with no chat history

Written 2026-09-04 at the maintainer's request, at the end of the session that
shipped A1 and B1, repaired the factory dispatch outage, and filed the spec
proposal that outage exposed. Its purpose is narrow: a fresh session should be
able to open this file and put six decisions to the maintainer without
reconstructing anything.

Read this with `bd show livespec-dev-tooling-efqeip` open. The plan is 6 of 10
children closed. Nothing here is a status queue — the ledger is the status.
These are the points where the plan needs a person.

Ask them ONE AT A TIME, in the order below, and record each answer where the
decision names. Each carries a recommendation, because a question you can
answer with a recommendation is a finding, not a question.

---

## D1 — The charter's third acceptance criterion has no evidence path

**Blocked:** `livespec-dev-tooling-mlg5sf` (cache telemetry, pod side), and
through it the charter's own acceptance.

**The situation.** The charter asks for three things: the console matrix at or
below the hosted warm baseline, the PR lane proven unable to write the trusted
cache, and a second routed repository benefiting with zero workflow changes.
The first two are met on SINGLE-RUN, hand-read evidence. The third is not met
at all, and the standing-query form of the first needs the same mechanism: the
per-job `cache.warm-copy` and `cache.job-summary` spans that `mlg5sf` emits.

Those spans need a keyless OTLP endpoint the job pods can reach. That endpoint
is not this plan's to build. It is carried by `livespec-vwzv` in the `livespec`
repo, verified 2026-09-04 as **P1, BACKLOG, not started**. Nothing in this plan
can move it.

**The options.**

1. Pick up `livespec-vwzv` (or the narrower listener it contains) as the next
   real piece of work, from whichever session owns that repo. Unblocks `mlg5sf`
   properly and gives the charter a standing query rather than an anecdote.
2. Accept the single-run hand-read numbers as sufficient evidence for this
   plan's acceptance, close `mlg5sf` as deferred, and let the standing query
   arrive with `livespec-vwzv` whenever it does.
3. Leave both parked and accept that the plan cannot be archived.

**Recommendation: 1.** The plan already discovered, at real cost, what happens
when a green artifact is trusted in place of the thing it stands for. Option 2
repeats that shape at the level of the charter's own acceptance. Option 1 is
also cheap relative to what has already shipped, and `livespec-vwzv` is P1 in
its own repo for reasons of its own.

**If 2 is chosen,** say so explicitly on the epic, because the archive gate's
completeness review will otherwise read the missing third criterion as
incomplete coverage and refuse.

---

## D2 — The keyed-tier proof answers a charter question nobody has answered on the pool

**Blocked:** `livespec-dev-tooling-dajhxa`. Not blocked by any dependency. It
needs authorization, because it mutates the host.

**The situation.** The charter's first open question is whether the
forked-runner cost of a keyed local cache is real TODAY, and it records that
the maintainer was skeptical of the claim and asked for it to be re-verified.
`research/002` answered it from the runner source. `dajhxa` is the on-pool
empirical half: a scratch scale set with a `NODE_OPTIONS` preload plus a
falcondev cache server in a scratch `ci-actions-cache` namespace, one routed
job with an `actions/cache` step, then record whether the save lands locally
and whether artifact upload and download still pass through.

The scope event marks it offered-not-required, and two sessions have now
deprioritized it on that basis. It is nonetheless the only remaining child that
answers a question the charter actually asks.

**The options.**

1. Authorize the experiment on the `research/005` pattern: scratch namespace,
   measured, deleted, nothing converged.
2. Drop it and close the child, letting the source-read answer in
   `research/002` stand as the charter's answer to open question 1.
3. Keep deferring.

**Recommendation: 1, at low priority.** It is roughly an hour, it is
self-contained, and its result either re-opens tier 2 as cheap or retires the
question for good. Option 3 is the one to avoid: a deferred item that keeps
being deferred is how the charter's own question quietly goes unanswered.

**Note for whoever runs it:** it creates cluster objects. That is why it is a
question and not something a session takes on its own.

---

## D3 — The conformance gate is a silent no-op in twelve of fourteen fleet repos

**Blocked:** `bd-ib-i7ag` in `livespec-orchestrator-beads-fabro`, P1, blocked,
needs-human. Not a child of this plan, but it will bite the plan's first
working dispatch.

**The situation.** Commit `39526e5c` (2026-08-31) turned five previously
hardcoded prepare commands — the version-manager install, the hook-manager
install, the commit-refuse hook install, and the two conformance verifiers —
into projections of each governed repository's own declaration, whose fleet
default is the ratified explicit NO-OP. Adoption never followed. Counted across
the fleet's fourteen `.livespec.jsonc` files, read INSIDE the
`livespec-orchestrator-beads-fabro` plugin block where the keys actually live,
one repository had adopted them, and it was the schema author. This repository
adopted on 2026-09-04. Twelve remain.

For each unadopted repository, a dispatched sandbox installs no pinned
toolchain, no hook manager, and neither installs nor verifies the structural
commit-refuse hook that fires the Red-Green-Replay gates on every in-sandbox
commit — while the check suite still resolves to `mise exec -- just check` from
its own fleet default. Nothing fails. The run proceeds and reads green.

Only three of the five undeclared premises warn at dispatch time. The two
toolchain ones go to no-op in silence.

**The options.**

1. Per-repo adoption: declare the five in each of the twelve remaining repos.
   Correct per repo, twelve edits, and a NEW adopter still defaults to a
   silently gutted gate.
2. Change the fleet default for FLEET MEMBERS: a repository carrying the
   `livespec-dev-tooling` package inherits the internal invocations rather than
   the no-op, leaving the ratified no-op as the default for genuine external
   adopters, which is the case it was designed for.
3. Fail closed: refuse to dispatch a repository declaring none of the five, so
   the choice is always explicit.

**Recommendation: 2.** It makes silence safe rather than dangerous, which is
the property the current shape gets backwards, and it does not punish external
adopters. Whichever is chosen, make the two toolchain premises warn like the
conformance trio, and add a check that a fleet member's resolved conformance
premises are non-empty.

**Note:** option 2 is a further spec change in the orchestrator repo, and it is
an explicit non-goal of the proposal filed as D4 below. Do not bundle them.

---

## D4 — A spec proposal is pending that the shipped code already depends on

**Blocked:** ratification of
`SPECIFICATION/proposed_changes/host-rendered-prepare-step-inputs.md` in
`livespec-orchestrator-beads-fabro` (merged as `ac52ce36`, PR #2133).

**The situation.** That repo's ratified clause requires every `inputs.*` token
to "sit in a position the engine renders". Since `39526e5c` the seam check has
classified the prepare-step position as rendered while the engine does not
render it — the inverse of the clause, and the reason a total dispatch outage
stayed invisible for four days. The fix (`79066c79`) made the underlying claim
TRUE by rendering host-side in the Dispatcher's overlay, so behaviour is now
correct and the ratified wording is not.

The proposal widens the criterion to "resolved before the sandbox executes it",
admits exactly two resolvers, requires the check to record WHICH resolver each
position depends on, requires an overlay-resolved position to be backed by a
real substitution, and states the residual limit that this check cannot
establish what the pinned engine renders.

**The options.** Ratify as proposed; ratify with modifications; reject and
revert the code to match the existing clause.

**Recommendation: ratify as proposed.** Rejecting means reverting a fix that
demonstrably restores every dispatch in the fleet, to satisfy wording that has
not described the payload since August.

**Where:** a `/livespec:revise` pass in `livespec-orchestrator-beads-fabro`, not
here.

---

## D5 — Whether the per-repo target cache stays deferred

**Blocked:** `livespec-dev-tooling-c5byjh`, waiting on `livespec-e2vcqf` in the
`livespec` repo, verified 2026-09-04 as **P2, BACKLOG, not started**.

**The situation.** B2 was REJECTED on the array by the start-burst evidence and
deferred until the CI work volumes sit on the NVMe, where the byte copy can be
measured honestly. That is a recorded scope decision, not drift.

**The options.** Leave deferred until the storage item lands; or re-prioritize
the storage item to unblock it; or close B2 permanently on the grounds that
sccache already carries the win.

**Recommendation: leave deferred.** This is the one blocker that is correctly
parked. The measurement it needs cannot be taken on the current medium, and
`research/006` shows the sccache tier already delivers the matrix number.

---

## D6 — What closes this plan

**Blocked:** the archive gate.

**The situation.** Archiving needs two things: every child disposed, and
durable independent completeness-review evidence recorded on the epic. Four
children are open (`npsqeu`, `mlg5sf`, `c5byjh`, `dajhxa`), and no review has
been commissioned. Separately, the CROSS-REPO half of factory parity — the
receiver allowlist admitting `build.cache.*`, the sandbox resolving the pool's
two service names, the sccache mount, the `/.cargo/config.toml` — is a
requirement carrier with NO CHILD ANYWHERE since `npsqeu` was narrowed to this
repository's half. It must be filed in the orchestrator's ledger before
`npsqeu` closing can be read as factory parity being complete.

**The question.** Does the plan archive once D1, D2 and D5 are settled and
their children disposed, or does it stay live until the cross-repo half is also
filed and closed?

**Recommendation: stay live until the cross-repo half has a carrier.** The
plan's archive rule already says work may only be transferred out if the
archive record names the follow-ups exactly. Filing that child is cheaper than
writing a transfer record for it.

---

## What is NOT blocked, and should just be done

`livespec-dev-tooling-npsqeu` is unblocked as of 15:29Z: the dispatcher fix is
released as v0.124.3 and a plugin build carrying it is on disk. The child still
sits at `blocked / blocked-reason:infra-external` only because this session
stopped before re-dispatching it. Move it to ready and run
`drive --action impl:livespec-dev-tooling-npsqeu`, then record the run id on
`bd-ib-8atx` as its final acceptance criterion and close that item.

Do D3 before trusting that run's conformance behaviour. The dispatch will work;
it will also skip the commit-refuse install in any unadopted repository and
report success.

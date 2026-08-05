# Fleet shell quality enforcement — CLOSING RECORD

**Status: COMPLETE and ARCHIVED.** Ledger anchor: epic
`livespec-dev-tooling-42t4az`. Closeout: `livespec-dev-tooling-qgw7gb`.

This replaces the live restart handoff. The prior text served session-to-session
resumption and is preserved in git history; what follows is the durable account of
what shipped, what it cost, and what it taught.

## What shipped

Mechanical shell-quality enforcement across all nine fleet repositories: a canonical
`check-shell-quality` gate with a pinned ShellCheck `0.11.0`, wired into each tenant's
`just check` aggregate and its CI matrix, with governed justfile recipe bodies migrated
out of inline shell where the policy required it.

**Eight of eight rollouts closed with merge evidence:**

| tenant | work-item | evidence |
|---|---|---|
| driver-claude | `livespec-driver-claude-gtqrzu` | PR 410, `0f0e348e` |
| driver-codex | `livespec-driver-codex-bedeju` | PR 388, `e3077796` |
| beads-fabro | `bd-ib-35qhta` | PR 1290, `ad09ca85` |
| git-jsonl | `bd-gj-uworva` | verified revert/fix/reapply ending `753f673f` |
| console | `livespec-console-beads-fabro-6yii4r` | PR 635, `305b59ee` |
| overseer | `overseer-cdhdlv` | PR 686, `9825253d` |
| livespec | `livespec-akg7k5` | PR 2018, `18eeedc4` |
| runtime | `livespec-runtime-ohlb4f` | PR 467, `25d300f9` |

Epic children: `.1` closed (missing-shellcheck `TypeError`), `.2` closed on its
recorded-finding branch, `.3` closed (the fanout silent-skip, PR 1281 / `ac5defd1`),
`.4` closed.

## The finding that mattered most

The gate this epic shipped was itself unsound, and the epic's own closeout controls are
what exposed it.

`shell_quality._mentions_errexit` gated the documented-deviation exemption on
`"errexit" in text or "-e" in text`. That second disjunct is a **two-character
substring**: any ordinary hyphenated word in a recipe's doc bought the exemption a real
rationale is supposed to earn. The live instance was **this repo's own flagship `check:`
aggregate**, exempted by the hyphen in `byte-for-entry`. Measured across all nine
justfiles, it was the only occurrence — and the worst possible one.

Fixed in `livespec-dev-tooling-gmwckx` (PR 1277, `1969bc85`) as a word-bounded match,
together with the recipe's own doc line, since repairing the matcher alone would have
turned this repo's gate red. The adversarial control that caught it is committed as a
regression test, demonstrated failing before the fix and passing after.

**Consequence for anyone reading the closeout as a clean bill of health:** every
shell-quality measurement taken before `1969bc85` was licensed by a discriminator that
could be satisfied accidentally.

## Acceptance, walked against the ledger text

1. **Armed-gate controls — PASS.** A failing ShellCheck control and the
   documented-versus-accidental recipe controls, plus a known-clean control and an
   adversarial fifth, run against the real checker over synthetic git fixtures. A and C
   convict; B and D stay silent; E flips FAIL→PASS across the `gmwckx` fix. Harness:
   `tmp/overseer/fleet-shell-quality-enforcement/qgw7gb_armed_gate_controls.py`.
2. **Zero findings across nine fetched master refs — PASS, WITH SCOPE.** Measured at
   immutable fetched refs via a detached worktree per tenant. **This is a zero in what is
   COMMITTED — a CI-view zero.** It is silent about shell this repo SHIPS into consumers
   where the gate structurally cannot see it: `42t4az.4` established with a clean control
   that a LOCAL view of git-jsonl reported six findings from the gitignored
   `worktree_pack` fragment. Do not restate this as "the fleet's shell is clean."
3. **Eight of eight rollouts closed with merge evidence — PASS.** Table above.
4. **Archived by merged PR with the primary clean — this commit.**

## What this thread learned, at cost

Four instances of one pattern, **the visible surface reports fine while something never
happened**:

- the masked `set -uo pipefail` recipe that started the thread — a suite whose failures
  could not turn it red;
- `42t4az.3` — the fanout projected the ShellCheck pin, then silently dropped the wiring
  and the CI job via `grep -q … || (::notice:: ; exit 0)`, exiting green;
- `gmwckx` — the exemption bought by a hyphen;
- `bd-ib-zp2axi` — the factory boundary DROPS a workflow change while the PR body reads
  complete, the mirror shape: a producer reporting success for work it deliberately did
  not do.

And a fifth, recurring in the *measurement* rather than the code: **an empty result read
as a finding.** It nearly landed five separate false conclusions — a file-absence checked
at a path that never existed, a `bd show` against the wrong tenant, a `check-targets.txt`
zero that meant file-absent, a `gh --json files` empty array, and a `jq` filter comparing
an object to a string that could never match. The remedy that caught every one:
**run a positive control before treating silence as evidence.**

### The sharpest instance: this archive nearly deleted its own final deliverable

The commit that archives this thread was first staged on a base that predated
`42t4az.4`'s merge. Because `git mv` carries file content from its base, the staged
`why-this-shape.md` was the PRE-`.4` copy — 204 lines, containing "Worktree pack scope
decision" zero times, against master's 232 lines containing it once. **Merging the archive
as staged would have silently reverted the entire 28-line deliverable of the last child
this thread dispatched, hours after that child succeeded.**

It presents as a PURE RENAME, which is exactly where a reviewer's eye stops. No gate
catches it: the plan-thread checks pass, and the diff looks clean. It was caught only by
diffing the archived blob against master by hand.

Generalized: **an archive built on a stale base is a silent revert dressed as a move.**
After rebasing such a branch, re-diff every rename-preserved file byte-for-byte against
post-rebase master — re-running the gates does not catch it, because no gate examines
whether a moved file's content is current.

That this thread's own closeout nearly destroyed its own last piece of work, and was
stopped by measurement rather than machinery, is the most honest summary of everything
above.

Two operational rules earned the hard way:

- **A finished run is not a finished dispatcher.** `succeeded/completed` plus a live
  lock-holding pid means the tenant is still occupied.
- **Tenant occupancy is a property of live processes and locks, not of ledger status.**

### The thesis, validated on the epic's own authors

The strongest evidence for everything above is that **the people who spent two days
writing these conventions needed the machinery to enforce them on themselves.** Twice in
one morning, on the closing day:

- The **pre-commit aggregate refused a duplicate patch.** A fix was ordered and started
  against a shipped fleet gate without first searching whether the defect was already
  filed — it was, eight hours earlier, as `livespec-dev-tooling-62jh` with PR 1290 already
  open. The hooks rejected the commit before it could become a second competing patch to
  the highest-blast-radius file in fleet pin distribution.
- **`livespec_footgun_guard` refused a `--no-verify`.** It was typed reflexively while
  composing a chained command — not under pressure, not as a judgement call. The
  supervising role had ended *every single message of the session* with "never pass
  `--no-verify`". The stated convention did not prevent the reflex. **The mechanical guard
  did.**

A gate that only ever catches other people is untested. Both of these caught their own
authors, which is the only test that counts.

This also adds a failure mode the rest of this record does not contain. Every other
finding here is *a check that never ran* — a silent skip, an unarmed gate, a scan that
excluded what mattered. This one is the inverse: **a human reaching past a check that
would have run.** Reflexive flag-typing during command composition is a distinct risk from
anything else catalogued above, and it has the same remedy — the guard, not the
convention.

## Defects filed, not absorbed

- `bd-ib-zp3u7y` — a dispatch dying before merge leaves its item `active` and invisible
  to needs-attention; the lane misses both ends of the axis (no outcome record, and an
  outcome record with a null `merge_sha`). Reproduced live, twice.
- `bd-ib-zp2axi` — the factory boundary's missing dropped-diff report.
- `bd-ib-hote` — review findings never reach the disposition prompt; three recurrences
  in one day, one of which discarded ~32 minutes of green work with nothing published.
- `livespec-dev-tooling-qn3pgi` — carrier for the `.2` mirror-retirement condition, so it
  stays visible rather than archived inside a closed item.

The `check-public-api-result-typed` red master across beads-fabro, git-jsonl and runtime
was **deliberately not absorbed**; it belongs to the `livespec-dev-tooling-8o8e` chain,
which restored those masters under a scoped unbreak. `ohlb4f` was blocked ~18 hours by
that red master alone and closed on the first reconcile once it cleared.

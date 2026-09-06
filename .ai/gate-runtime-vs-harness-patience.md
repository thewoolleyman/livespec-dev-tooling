# Gate runtime vs harness patience

Read this before running `just check`, committing product `.py`, or
diagnosing a gate command that "did nothing".

## The failure this closes

`.claude/settings.json` commits `BASH_MAX_TIMEOUT_MS=1200000` — a hard
20-minute ceiling on a single Bash tool call. The commit aggregate
(`scripts/just/check-pre-commit.sh` → `just check` → the ~44-target
`parallel_check_dispatcher`) measures **593s and 1043s on an unloaded
host** and **exceeds 1200s under sustained fleet load**.

When it exceeds the ceiling the harness kills the tool call and the
agent receives **no exit code, no hook output and no verdict**. Under
sustained load this repo therefore became *uncommittable for product
`.py`* — and it failed **silently**.

**The silent kill is the worse half.** A kill with no verdict looks
exactly like a hook refusal. Both present as "the commit did not
happen, and here is no useful output". Telling them apart used to
require going and checking by hand whether any check target had
actually run. Three amend attempts were lost to that ambiguity in one
session before anyone realised no hook had ever refused.

Those two states demand **opposite** responses:

| what happened | what it means | what to do |
|---|---|---|
| the gate **refused** | a real verdict — a check failed | fix the cause; never retry blind |
| the gate **did not finish** | no verdict exists | re-run it; conclude nothing |

Reading a kill as a refusal sends you hunting a defect that does not
exist. Reading a refusal as a kill sends you retrying a commit the gate
has already rejected. Neither may be guessed.

## The mechanism: `dev-tooling/gate-run.sh` (pack-materialized)

Gate **runtime** is decoupled from harness **patience**. The gate runs
in its own detached session that outlives the tool call; a separate,
cheap, restartable waiter reports the verdict when it lands.

```bash
# 1. launch — returns in well under a second, so run it FOREGROUND
run_id=$(mise exec -- just gate-start -- mise exec -- git commit --amend --no-edit)

# 2. wait — hand THIS to run_in_background: true
mise exec -- just gate-wait "$run_id"

# other verbs
mise exec -- just gate-status [run_id]   # one-shot verdict, never blocks
mise exec -- just gate-list              # recorded runs + derived state
```

`gate-wait` is the thing you background, not the gate. Killing the
waiter does not touch the gate — re-issue `gate-wait` and you get the
same verdict. That is what makes the harness ceiling irrelevant instead
of merely larger.

### A FRESH worktree has no `gate-start` until you materialize the pack

`gate-run.sh` and the `gate-*` recipes live in `dev-tooling/`, which is
**gitignored and materialized per worktree**. A worktree created with a
plain `git worktree add` therefore has neither: `just --list` shows no
`gate-*` row, and `just gate-start` fails as an unknown recipe. The
`justfile` imports the fragment with `import?` rather than `import`, so
a missing pack **silently no-ops** instead of erroring — which is why
the recipes read as absent rather than uninstalled.

```bash
mise exec -- just install-worktree-pack   # from INSIDE the new worktree
```

This bites hardest exactly where it matters most: the PreToolUse
background guard refuses to let a gate command (`git commit`,
`git push`, `gh pr ...`, `just check*`) be backgrounded bare and points
you at `gate-start`, so without the pack you are wedged between a hook
that forbids one route and a recipe that does not exist on the other.
Install the pack; do not reach for a foreground gate run instead.

The same applies in every fleet repo carrying the pack, `livespec`
included — the fragment is shipped by `livespec_dev_tooling`, not by the
consuming repo.

### What this does NOT change

**Nothing is weakened.** The same command runs, with the same hooks,
over the same targets, and every verdict is still honored — the gate's
own exit code IS the verdict and the runner only transports it. What
changed is how long the harness is willing to wait, not what runs or
what a failure means.

In particular a run that does not finish can **never** read as a pass.

## How "did not finish" reports itself

The run directory is written by the gate's own process, not by the
agent, and it is the evidence:

| file | written when | what it proves |
|---|---|---|
| `started_at` | before the gate starts | a run was launched |
| `pid` | by the child, as its first act | the gate has a live process |
| `output.log` | streamed during the run | these targets ran |
| `exit_code` | **only** on real completion | a verdict exists |

It lives under the **primary checkout's** `tmp/gate-runs/<run-id>/`,
resolved from the shared git dir (`git rev-parse --git-common-dir`) —
**not** under the worktree that started the run. It used to be the
latter, and routine post-merge `git worktree remove` then deleted the
only record of what a gate was executing when it failed
(livespec-dev-tooling-trfzkw). Because every worktree of a repository
resolves the same store, `gate-list` / `gate-status` / `gate-wait` see
the same runs from the primary and from any sibling worktree, and a run
outlives the worktree that started it. One store means the record has to
say *where* a run ran, so it also carries a `worktree` file, surfaced by
`gate-status` beside the command line.

`exit_code` present is the single marker of a verdict. Every terminal
state derives from those four files with no ambiguity left:

| condition | state | meaning |
|---|---|---|
| `exit_code == 0` | `PASSED` | ran to completion, passed |
| `exit_code` 1–127 | `FAILED` | **a real verdict** — honor it |
| `exit_code` ≥ 128 | `DIED_WITHOUT_VERDICT` | killed by signal; a signal death is not a check verdict |
| no `exit_code`, pid alive | `RUNNING` | no verdict yet |
| no `exit_code`, pid dead | `DIED_WITHOUT_VERDICT` | killed before it could decide |

`DIED_WITHOUT_VERDICT` exits **75** (`EX_TEMPFAIL`) — distinct from both
0 and the gate's own failure codes, so it can be neither mistaken for a
pass by an exit-status check nor mistaken for a refusal.

`gate-status` also reports **how many check targets completed**, parsed
from the dispatcher's `::: just <target> [ok|FAILED, wall: Ns]` lines.
That is the mechanical answer to *"did any target actually run"* — the
question that previously had to be reconstructed by hand each time.

## Working rule

**Exit status is not evidence, and neither is silence.** Before
concluding anything from a gate, name which of the five states you are
in. If you cannot, you do not have a result yet — you have an
unfinished run.

`tmp/` is gitignored: run records are host-local evidence and are never
committed.

Each run also carries a `.git/config` write-watch (livespec-p32m6d).
`core_before` / `core_after` digest the **primary's** shared `[core]`
block around the gate; a dependency-free background poller appends to
`config-writes.log` whenever that config changes or its lockfile
appears, naming the writer as far as `/proc` allows (current
`core.bare`, the gate child's descendant process tree, any `/proc/*/fd`
holder). When before and after differ, a `CORE_BARE_FLIP` marker is
written and `gate-status` prints it loudly.

**The flip is not a verdict.** The gate's own exit code is passed
through unchanged, the watch is failure-tolerant by construction, and
the existing `core_bare_is_true` remedy still heals the primary. The
watch answers *who wrote the config*, which the 03:00:09Z incident on
2026-09-06 could not answer at all.

## What was deliberately NOT done

- **Not raising `BASH_MAX_TIMEOUT_MS`.** It may be harness-enforced
  regardless, and a larger ceiling is still a ceiling — it postpones the
  same silent kill rather than removing it.
- **Not scoping the aggregate to changed targets.** That narrows what
  runs. It is a real idea and it needs its own argument on its own
  merits; it is not a fix for a timeout.
- **Not waiting for quiet windows.** Load is other lanes' behavior, not
  a property this repo controls.

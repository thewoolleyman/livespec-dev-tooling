# Agent instructions

## Codex dogfooding (OpenAI Codex CLI/TUI)

This repo's `/livespec:*` and orchestrator surfaces can be dogfooded from
OpenAI Codex CLI/TUI, not just Claude Code. Unlike the Claude path (plugins
enabled PER PROJECT via a committed `.claude/settings.json`), Codex plugin
enablement is **HOST-WIDE**: each registration persists in `~/.codex/config.toml`
and applies to every project on the host. Codex offers no project-scoped plugin
enablement, so there is no committed-settings analogue for the Codex path.

Install the three fleet plugins host-wide: livespec CORE (the artifact carrier
that ships the spec-side prose and wrappers), the `livespec-driver-codex` Codex
Driver (which supplies the `/livespec:*` operation surface over core's prose),
and the selected orchestrator plugin:

```bash
# livespec CORE (spec-side prose + wrappers; no skills of its own):
codex plugin marketplace add thewoolleyman/livespec
codex plugin add livespec@livespec

# The Codex Driver (supplies the spec-side /livespec:* operation surface):
codex plugin marketplace add thewoolleyman/livespec-driver-codex
codex plugin add livespec@livespec-driver-codex

# The selected orchestrator plugin (ships its own Codex skills):
codex plugin marketplace add thewoolleyman/livespec-orchestrator-beads-fabro
codex plugin add livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro
```

Once installed, Codex operations are driven via `codex exec` and NAME-selected as
`<plugin>:<op>` (for example, `livespec:next`,
`livespec-orchestrator-beads-fabro:list-work-items`) rather than as
`/`-prefixed slash commands. The distributed Drivers resolve their prose at
runtime; no `AGENTS.md` skill-to-prose mapping is required. See
`livespec/SPECIFICATION/contracts.md` §"Plugin distribution" and
`livespec/SPECIFICATION/non-functional-requirements.md` §"Codex dogfooding
contracts" for the authoritative install and resolution contracts.

The Codex TUI picker displays skills by short name with the plugin as context.
In `/skills` → `List skills` (or the `@` picker), search the operation name,
for example `orchestrate`; the row renders as
`orchestrate (livespec-orchestrator-beads-fabro)` with kind `Skill`. The
colon-qualified form `livespec-orchestrator-beads-fabro:orchestrate` is still
valid for prompt / `codex exec` name selection and model-visible skill
references, but it is not the picker row operators should expect.

## Progressive durable guidance

This file carries the always-load instructions. Load the sibling guidance files
only when their topic is active:

- Read `.ai/livespec-operation-gotchas.md` before running or editing
  livespec revise/propose-change flows, spec heading coverage, or commit-prefix
  classification logic.
- Read `.ai/fleet-and-secrets.md` before changing fleet coordination workflows,
  maintainer signaling, GitHub App automation, or 1Password-backed secret
  projection.
- Read `.ai/ci-node-storage-tiers.md` before touching the CI runner node's
  storage tiers (`ci-cache`, `ci-containerd`, `ci-workvols`), installing or
  surveying NVMe hardware on the node, or running anything under
  `ci-runner/k3s/phase2/storage-layout/` — the media-swap model, the link
  survey that is the acceptance test for any card or socket change, and the
  udev / fio / stale-copy traps that each cost real time on 2026-09-04.
- Read `.ai/gate-runtime-vs-harness-patience.md` before running `just check`,
  committing product `.py`, or diagnosing a gate command that produced no
  output — the commit aggregate can outlast the harness's 20-minute tool-call
  ceiling, and a kill with no verdict is NOT a hook refusal.

## Decision authority — when to ask, proceed, or self-resolve

Fleet-standard guidance, ported from `livespec/AGENTS.md` ("When to ask,
proceed, or self-resolve") and `livespec-orchestrator-beads-fabro/AGENTS.md`
("Drive authorized work to completion; do not over-ask"). The default is to
decide and report, not to escalate.

- **Drive authorized work to completion; do not over-ask.** When the maintainer
  names a goal and says to finish or continue it, execute the WHOLE arc —
  implement, dispatch, PR, merge, iterate, archive — without pausing to confirm
  each already-authorized step. An operator-flow step that says "present options
  and let the user select" is satisfied by a standing directive once the goal is
  named; do not re-prompt. Default to acting, then reporting outcomes.
- **Research before gating.** If a question is answerable by reading the code,
  the spec, the docs, or by testing on a live system, do that, decide,
  implement, and report for objection. Reserve gates for genuine product or
  values calls, irreversible or outward-facing actions, and secret or
  host-mutation authorization.
- **Only ask on genuine doubt, one thing at a time.** Self-resolve trivial
  wording fixes, internal-consistency repairs, and items clearly aligned with
  established preferences, presenting each with its disposition. When a gate is
  warranted, ask exactly one question per turn.
- **One investigation, one finding, one question.** When a focused investigation
  surfaces unrelated discrepancies, finish the original question first and
  surface only the load-bearing finding; log side observations briefly. Cosmetic
  drift never blocks on its own.
- **Prescribed destructive ops are pre-authorized.** When a destructive git
  operation is the codified mechanism of an adopted workflow — the
  `git commit --amend` of the Red→Green step, for instance — the adoption is the
  authorization. Keep per-instance gating for ad-hoc `--amend`, force-push,
  `reset --hard`, or `branch -D` on unmerged branches.

Two rules this repository earned the hard way, from the 2026-08-20 stall
investigation:

- **An unratified filter inside a check is conformance, not ratification.**
  Narrowing, excluding, or filtering inside an enforcement check to match what
  the ratified spec already says is a conformance fix — implement it and report
  it. It only becomes a ratification question when the change would make the
  check assert something the spec does not.
- **A question you can answer with a recommendation is a finding, not a
  maintainer question.** If you can state the options, the costs, and which one
  you would pick, you have already done the deciding work. Decide it, record the
  reasoning where the work is tracked, and report it as decided.
- **"Decide them from a fresh context" means the fresh session decides.** When
  a handoff records that the maintainer asked for a plan's blockers to be walked
  and DECIDED from a fresh context, the new session's uncontaminated judgment is
  the decision mechanism; a research note that already carries a recommendation
  per item is a set of findings, not a questionnaire. Read the maintainer's
  direction in the handoff, not the prior session's paraphrase of it into a
  next action — if the two disagree, the direction wins. Decide each item, do
  the research the decision needs (on 2026-09-04 one of six rested on a
  misidentified blocker and changed on verification), record each answer where
  the item names it, execute the consequences, and report for objection. The
  2026-09-04 resume opened by putting decision 1 back to the maintainer as a
  picker and was told, bluntly, that this was the wrong thing.

## Ordering — confirm the reader before you write

The decision-authority section above says WHO decides. This one says WHEN a
write is safe to make:

> **Never write durable state into a component you have not first confirmed is
> running the code that preserves it.**

Stated alone this reads as obvious. It is recorded because it is not: it cost
real work three times on 2026-08-20, in three unrelated subsystems, each time
rediscovered from scratch by a session that would have agreed with the rule if
asked. In two of the three, the reversed order DESTROYED SOMETHING RECOVERABLE —
that is what separates this from an ordinary sequencing preference. Writing
early is not merely wasted; it can consume the budget that would have let you
retry.

- **Arming a check ahead of adoption — the one this repo actually paid for.**
  The Railway decoupling landed in `46c5dab`, turned FIVE repos red, and was
  reverted in `f4247110`. `plan/rop-railway-enforcement/` now carries the
  standing constraint "Do not arm the check anywhere", because a check armed
  before the repos it judges have adopted the shape is a check writing verdicts
  into a fleet that cannot satisfy them. Adoption first, then arming.
- **Writing a seat anchor into a seat mid-build.** A foreman wrote a console
  seat's anchor epic at 05:49Z into a seat still executing a build whose
  `register_foreman_track` delete-and-recreates that row. The write was doomed
  at the moment it was made; the epic died at the 06:29:50Z tick, and the
  failure presented as nothing having happened at all — the worst shape, because
  silence is indistinguishable from success.
- **Re-running acceptance against an unfixed matcher.** `reconcile-merged` must
  run only AFTER the criteria defect that caused a false rework is fixed. Run
  against unfixed criteria it fails identically — but unlike the first failure,
  that one REACHES the matcher and spends the last rework attempt, converting a
  recoverable item into a blocked one.

How to apply it: before a durable write, name the component that will hold the
state and establish that the code it is currently running is the code that
preserves it. "It was deployed" is not that; "the version now serving is the
version with the fix" is. When you cannot establish it, the honest move is to
wait — waiting is not a maintainer question. And note the shared failure mode
across all three: the destructive case is SILENT, so the absence of an error is
not evidence the write survived.

## Ledger access needs the credential wrapper

The beads ledger for this repo is a per-repo TENANT database, and its password
is projected from 1Password rather than stored on disk. A bare `bd` therefore
fails with:

```text
Error: failed to open database: failed to check if database
"livespec-dev-tooling" exists on server 127.0.0.1:3307:
Error 1045 (28000): Access denied for user 'livespec-dev-tooling'
```

That signature is a MISSING CREDENTIAL, not a store outage, not a corrupt
database, and not a reason to start diagnosing the Dolt server. Re-run through
the installed wrapper:

```bash
/usr/local/bin/with-livespec-env.sh -- bd show <work-item-id>
```

Three sessions independently lost a diagnostic cycle to this on 2026-08-19 and
2026-08-20. Read `.ai/fleet-and-secrets.md` for the full projection story
(1Password environment id, encrypted service-account token, wrapper factory
repo) before changing anything about how the secrets are injected.

## Repository mutation protocol

Every repo change uses a worktree → PR → merge → cleanup path. Treat
leaving dirty state, committing on the primary checkout, or asking the
user whether to commit as failures of the workflow, not as acceptable
stopping points.

1. Confirm the primary checkout before editing:

   ```bash
   git -C /data/projects/livespec-dev-tooling config --get livespec.primaryPath
   git -C /data/projects/livespec-dev-tooling status --short --branch
   ```

2. If the change will modify tracked files, create a dedicated worktree
   from the primary checkout's `master` and do all edits there. Every
   fleet worktree lives under the per-user root `~/.worktrees/<repo>/<branch>`
   (never a peer of the clones in `/data/projects`); `just bootstrap`
   registers `~/.worktrees` in mise's `trusted_config_paths`, so a
   freshly created worktree's `.mise.toml` auto-trusts and the first
   `mise exec` inside it never stops on the "config not trusted" prompt:

   ```bash
   mise exec -- git -C /data/projects/livespec-dev-tooling worktree add -b <branch> "$HOME/.worktrees/livespec-dev-tooling/<branch>" master
   ```

3. Use `mise exec -- git commit ...` and `mise exec -- git push ...` so
   the mise-managed lefthook hooks actually run. Never pass
   `--no-verify`; if a hook fails, fix the cause or halt with the
   failure.
4. Open a PR, wait for required checks, and merge through the PR using
   the repo's rebase-merge discipline.
5. After merge, refresh `/data/projects/livespec-dev-tooling` to
   `origin/master`, remove the feature worktree, delete the local
   branch, and verify the primary checkout is clean on `master`.

Do not leave orphaned worktrees. If a session must stop before cleanup,
record the active worktree path, branch, PR, validation state, and next
action in the relevant handoff document.

## Red-Green-Replay commit protocol

Product `.py` changes are committed via a 2-step single-commit TDD ritual,
enforced by the `red_green_replay` commit-refuse hook (it inspects the staged
tree and writes `TDD-*` trailers). The final result is ONE commit carrying the
test, the impl, and both trailer sets.

1. **Red commit.** Stage the test file ALONE — no impl — and commit with a
   `fix:`/`feat:` subject. The hook runs pytest on the staged tree; the staged
   test MUST fail on pytest (non-zero exit). An `ImportError` or a collection
   error counts as a failure to the hook, BUT you SHOULD prefer a genuine
   assertion failure so Red proves the behavior is actually unimplemented
   rather than merely unimportable — see the new-module stub technique below.
   It records `TDD-Red-*` trailers (test path, failure reason, test-file
   checksum, output checksum, captured-at).
   - Gotcha: the impl must be UNMODIFIED on disk at the Red commit, because the
     hook's pytest reads the on-disk module. If the impl already carries the
     change the test passes, and the hook rejects with `test-passed-at-red`.
2. **Green amend.** Stage the impl and run `git commit --amend`. The hook sees
   the `TDD-Red-*` trailers + the staged impl, re-runs the SAME test (now
   passing), and records `TDD-Green-*` trailers. The test file bytes MUST be
   byte-identical across the Red→Green pair; to change the test, author a fresh
   Red commit.

### Both legs run the full aggregate — run them DETACHED

Either leg can outlast the harness's 20-minute tool-call ceiling, and when it
does the kill produces NO verdict and looks exactly like a hook refusal. Dispatch
gate commands through the detached runner instead of a bare foreground call:

```bash
run_id=$(mise exec -- just gate-start -- mise exec -- git commit --amend --no-edit)
mise exec -- just gate-wait "$run_id"     # background THIS; killing it is harmless
```

`gate-wait` exits with the gate's own exit code, or **75** for
`DIED_WITHOUT_VERDICT` — the state that says the gate did not finish, which is
neither a pass nor a refusal. Never infer a verdict from silence. Read
`.ai/gate-runtime-vs-harness-patience.md` before diagnosing a quiet gate.

### New-module stub technique (avoiding false reds)

When the impl module under test does NOT exist yet, the natural Red would be an
`ImportError` or a collection error rather than an assertion failure. The hook
accepts that as a failing Red, but it does not prove the behavior is
unimplemented — only that the module is unimportable. To make Red fail on a
genuine assertion instead:

1. At Red time, create the impl module as a minimal **stub** on disk — enough
   that the test imports and runs, but its assertion FAILS (e.g. a function
   that returns a wrong/sentinel value, or raises `NotImplementedError` only
   when that still yields an assertion failure rather than a collection error).
2. The stub must NOT make the test pass — a passing test at Red trips the
   hook's `test-passed-at-red` gate.
3. Then the **Green amend** replaces the stub with the real implementation that
   makes the assertion pass.

This keeps Red honest: it proves the behavior is unimplemented, not merely that
the module is missing.

**Exempt:** changesets with no product `.py` (docs, spec, work-items, shell,
config) use `chore(...)` / `docs(...)` / `chore(spec):` subjects and skip the
ritual entirely. Always use `mise exec -- git ...` so the hooks fire; never
pass `--no-verify`.

## CI runner routing

This repo's gating CI reads the `CI_RUNNER_LABELS` repository variable
directly at each gating job's `runs-on`, with an inline
`|| '["ubuntu-latest"]'` fallback — the same pattern the other fleet repos on
self-hosted capacity use, and the posture ratified in
`SPECIFICATION/constraints.md` §"CI matrix shape" (v048). Reverting to hosted
is MANUAL: set the variable back to `["ubuntu-latest"]` or delete it.
Real production traffic on the `livespec-dev-tooling-k3s` scale set was cut
and proven 2026-08-18 (livespec-s43svm.23), completing the fleet's 8-of-8
k3s cutover sequence (livespec-s43svm.16).

This replaced a two-probe health-check router (`select-ci-runner` calling
`reusable-ci-runner-router.yml`, plus the `ci-runner-health` composite
Action), retired as `livespec-s43svm.23` because it CANNOT work against ARC
scale sets: `gha-runner-scale-set` runners register with an EMPTY label array,
so a label-subset probe never matches them, and the sets run `min-runners: 0`,
so an idle set has zero registered runners by design. Left in place it failed
its probe on every run and silently routed every job to hosted capacity
regardless of `CI_RUNNER_LABELS`.

Do NOT reintroduce a pre-flight label probe for ARC capacity. If automatic
failover is ever wanted again, it needs a mechanism that does not depend on
scale-set runners carrying labels or on a runner existing while the set is
idle.

See `docs/ci-runner-failover.md` for the operator-facing routing and fork-safety
detail, and
`livespec/plan/fleet-ci-runner-pool/research/k3s-arc-kueue-migration.md`
("Real-traffic cutover log") for the cross-repo record.

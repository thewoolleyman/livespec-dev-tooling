# Supervisor Handoff — worktree-location-enforcement

## HALT-first preconditions

Verify every precondition before doing anything else. Stop on the first failure
and report the exact expected name; do not improvise around it.

1. The supervised session is tmux `worktree-location-enforcement`. Verify it
   with `tmux has-session -t worktree-location-enforcement`.
2. The supervisor session is tmux
   `worktree-location-enforcement-supervisor`.
3. The supervised pane's process tree contains a live `claude` or `codex` CLI
   process. A tmux session that is only a shell is a failure. Establish runtime
   identity from the live process tree, never from the session name.
4. The target repository is `/data/projects/livespec-dev-tooling`, the worker
   pane's cwd resolves inside it, and
   `plan/worktree-location-enforcement/` exists.

## Role

You are the supervisor, not the implementer. Keep the thread moving, vet
decisions before they reach the maintainer, and protect the record's honesty.
Do not write the implementation, slice the epic without consent, or take over
the worker's branches and worktrees.

Hand analysis to the supervised session as **input to verify**. The worker must
verify it independently. If the worker's verification contradicts yours, you
are wrong and its verification wins; acknowledge the correction explicitly.

Relay only stable conditions from other tracks. Never copy volatile queue
ranks, in-flight disputes, or guessed ownership into this thread's durable
record.

### This thread's specific honesty hazard

This thread was parked after its analysis was measured at dev-tooling commit
`2412e21`. On 2026-07-25, `origin/master` was already at `183be4d`, 130 commits
later. The ledger epic `livespec-dev-tooling-0eo` still had zero children and
there was no topic implementation branch, worktree, or open PR, but those are
observations to recheck, not facts to inherit forever.

Before approving any old premise or proposing a cut, require the worker to:

- fetch the forge and remeasure against current `origin/master` in every
  affected repository;
- use livespec core's committed fleet manifest as the current membership source
  of truth, with repository topics only as a discovery safety net;
- recheck the governed-repository count, pack-install state, installed hook
  bytes, relevant config declarations, genuine nested worktrees, open PRs, and
  ownership of every branch or worktree it might touch;
- replace stale line anchors and counts in the handoff rather than quietly
  reasoning from them;
- distinguish durable tracked state from host-local state such as
  `.git/hooks/`; and
- rebase or supersede any surviving topic work on current `origin/master`
  before using it.

The old analysis remaining directionally correct is not enough. A "done" claim
must be based on current evidence and an enforcement proof that can turn red.

## How to inspect and drive

Sessions: `worktree-location-enforcement` (worker) and
`worktree-location-enforcement-supervisor` (you).

- Inspect read-only with
  `tmux capture-pane -p -t worktree-location-enforcement | tail -N`.
- Send a short instruction with one
  `tmux send-keys -t worktree-location-enforcement -- '<one line>' Enter`.
- For longer text, use `tmux load-buffer`, then `paste-buffer -t`, capture the
  pane to verify the paste landed, and only then press Enter.
- Idle plus queued input means stuck, not idle. Check for a modal, an open
  picker, or unsubmitted pasted text.
- An open `AskUserQuestion` picker is a real human gate and also suppresses the
  overseer daemon's wrap-up injection into that pane. Clear or answer it
  promptly.
- Never name a shell variable `TMUX`. Never run `tmux kill-server` on the
  maintainer's socket.

The first driving brief should ask the worker to refresh the parked thread,
produce a measured delta from the old handoff, and prepare—not presume—the
rollout-order and slice-cut decision. Do not dispatch implementation while the
epic has no approved children.

### No idle and no silent block

A stale premise, a conflicting lane, or another track's ownership blocks only
the affected action. Have the worker enumerate the remaining safe,
non-conflicting work and take the next concrete action. While the rollout
decision is pending, current-state measurement and a finished decision packet
remain legitimate work. Only declare the thread blocked when no in-scope safe
action remains, then surface exactly one prepared maintainer question.

## Decision-vetting rubric

Escalate only decisions that are both genuinely blocking and genuinely
human-facing. For this thread they include:

- rollout order for pack installation, verifier enforcement, canonical hook
  changes, per-clone hook reinstall, and the live-worktree relocation;
- the approved A–E slice cut and acceptance criteria;
- authority to relocate a worktree that may contain uncommitted work or belong
  to another live session;
- spec ratification; and
- billing or account choices.

Everything else stays with the worker. Require it to assemble evidence, cut the
real options, name a recommendation, state the failure window of each option,
and then surface the finished question rather than the raw problem.

For the old rollout-order question, do not accept a stale binary choice.
Require a current dependency graph that accounts for automatic release and pin
fan-out changes since `2412e21`, current fleet membership, and the fact that
canonical hook bodies are byte-compared per clone.

A supervisor may discharge an acceptance leg only after independently
verifying the forge artifacts and the live behavior, and recording that basis.
For this thread, acceptance evidence must include:

- required-pack absence fails while an explicit sanctioned opt-out behaves as
  specified;
- a worktree physically nested in the primary working tree is refused at
  commit time;
- a sanctioned worktree under `~/.worktrees/` still works;
- the `.git/` carve-out still permits beads' internal sync worktrees;
- physical-path aliases are covered with `pwd -P`;
- every governed clone's installed hook is current after the canonical body
  changes; and
- an injected defect makes the relevant verifier or test fail. A verifier that
  cannot fail is not a verifier.

## AskUserQuestion presentation rules

Ask one question per turn. Put the recommended option first and label it
`(Recommended)`. Use full repository names, never abbreviations the reader must
expand. Put `---` as the final line before the picker.

## Standing safety clauses

Repeat these in every instruction sent to the supervised session:

- Never pass `--no-verify`; halt and report on hook failure rather than working
  around it.
- Never touch another session's worktrees or branches.
- Every tracked-file change goes through a dedicated worktree, PR, required
  checks, rebase-merge, and cleanup; never commit on the primary checkout.
- Verify against the forge (`origin/master` after a fetch), never a working
  tree that may be stale. Rebase old work before relying on it.
- Preserve unrelated primary-checkout state.
- For product `.py` changes, obey the repository's Red–Green–Replay
  single-commit protocol exactly: test-only Red with implementation unmodified,
  then Green amend with unchanged test bytes.
- Before moving any worktree, inspect it for uncommitted work, establish its
  owning session, and obtain any authority the move requires.

For factory dispatches, also repeat:

- Prove container ownership from run-config argv across all containers, never
  from image shape, position, or timing.
- Treat `exit 137` as ambiguous between a kill and normal teardown.
- Establish outcomes from artifacts—merged PR, journal, and ledger—not exit
  codes.
- Build log timestamps with `date -u`, never by hand.

## Corrections

Record corrections to this supervisor's own behavior here; do not turn this
into a log of worker mistakes. This thread has had no active supervisor yet, so
the local log starts empty.

Role-level corrections carried from the overseer predecessor threads:

- Do not order fallback-less waits. Wrap-up is a consequence of useful work,
  not something to idle for.
- Relay only stable foreign-track conditions.
- Verify on the forge; absence from a stale checkout proves nothing.
- When the worker's verification contradicts the brief, the brief loses.
- Billing and account choices belong to the maintainer.
- A verifier must be able to fail; ask which injected defect makes it red and
  prefer to see that demonstrated.

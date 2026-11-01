# 002: the seat never blocks

This note amends the charter (note 001). Where they disagree, this note wins.

## The maintainer's ruling (attended, 2026-11-01 ~21:1xZ, verbatim)

"You've already failed in your dogfooding. You should be forbidden from presenting blocking pickers. You are only ever
supposed to run autonomously, never block. That is a failure in your plan. Fix it and make it impossible."

It is recorded as a scope event on epic livespec-dev-tooling-6tgd2z (`maintainer-ruling: no-blocking-pickers`).

## What went wrong

At about 21:0xZ this seat sent two decisions to the maintainer in a blocking AskUserQuestion picker and stopped while
it waited:

- the Dolt crash-recovery drill authorisation;
- the fabro-currency DoD-1 deferral.

The charter had said to "bring things to the maintainer only when necessary". It never said how, so the seat reached
for the picker, which parks the whole seat. The seat stopped, and nothing it watches moved.

## The rule

1. **Never present a blocking picker.** No AskUserQuestion, and no turn that ends waiting for an answer. The loop
   always keeps running.
2. **Decide what can be decided.** Anything answerable with a recommendation is decided under R301 and reported
   (see CLAUDE.md "Decision authority").
3. **Report what is genuinely the maintainer's, without blocking.** That means host mutation on a shared host,
   secrets, and values calls. Each one goes in the tick report as plain text under `FOR THE MAINTAINER (non-blocking)`.
   Each entry is written so it can be answered cold: what is needed, why, the options, and a recommendation. The item
   waits; the seat does not.
4. **Re-surface unanswered asks.** An ask stays in every tick report until it is answered. When the maintainer
   answers, the seat relays the answer verbatim to the owning seat.

The same rule binds legacy-dispatcher-agent.

## Enforcement (makes it impossible)

There is a user-scope PreToolUse hook:

- The script is `~/.claude/hooks/no-blocking-picker-guard.py`.
- It is registered in `~/.claude/settings.json` with matcher `AskUserQuestion`.
- It walks the process tree to the nearest `claude` ancestor and reads its `-n` name. When that name is
  `legacy-coordinator-agent` or `legacy-dispatcher-agent`, it denies the tool.
- It is user-scoped, not repository-scoped, because the dispatcher seat runs in livespec-orchestrator-beads-fabro.

Verified on 2026-11-01: a live AskUserQuestion test call from this seat was denied by the hook before it rendered.

## Tick report shape (amends note 001)

After DEPENDENCIES and the actions taken this tick, the report closes with:

```text
FOR THE MAINTAINER (non-blocking)
- <ask>: <what is needed> — <why> — <options> — recommend <x>. Waiting since <UTC>.
```

If there is nothing to ask, the section reads `none`.

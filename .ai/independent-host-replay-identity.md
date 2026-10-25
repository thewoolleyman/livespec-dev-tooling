# Launching an independent host-proof replay

A host-captured assertion is accepted only when a `host_verified` record from a
DIFFERENT party replays the `host_recorded` capture. `dispatcher.py
post-host-record` computes the publishing identity itself and refuses a replay
whose identity equals the capture's. It does not take the identity from its
caller, and `--invoker` does not change it.

## The trap: a child process inherits your session id

The identity resolver (`_dispatcher_proof_identity.py` in
livespec-orchestrator-beads-fabro) reads the agent-session variable first:
`CLAUDE_CODE_SESSION_ID`, then `CODEX_SESSION_ID`, then `PI_SESSION_ID`. It
falls back to the forge login only when none is set. A replayer that one
session launches from its own shell, such as `codex exec`, inherits that
session's `CLAUDE_CODE_SESSION_ID`. The replayer then resolves to the
capturer, and its `host_verified` post is refused as a self-replay.

Measured 2026-10-25 on livespec-dev-tooling-c62xtb. A codex replay reproduced
the assertion and was still refused, because it resolved to the identity of
the original capture. Nothing was posted, and the assertion stayed pending.

## How to launch one

Strip the inherited variables so that the replayer resolves its own identity:

```bash
setsid nohup env -u CLAUDE_CODE_SESSION_ID -u CLAUDECODE -u CLAUDE_CODE_ENTRYPOINT \
  codex exec --dangerously-bypass-approvals-and-sandbox -C <repo> "$(cat <brief>)" \
  > <log> 2>&1 < /dev/null &
```

This removes a WRONG identity; it does not choose one, so it is not a way
around the independence refusal. Brief the replayer with the assertion
verbatim and the steps to run, but never with the capture's results: the
replayer re-measures, and it may publish `host_not_reproduced`.

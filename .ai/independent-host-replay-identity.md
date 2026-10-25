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

## The second trap: the release tag must be a git tag of THIS repository

The acceptance pass accepts a replay only when the build it names contains the
item's merge. It reads `release_tag` first and falls back to `commit`, and it
asks the forge whether that ref contains the merge commit of the item's pull
request, in the repository that owns the item. A ref the forge cannot resolve
there is UNOBSERVABLE, and the replay is silently not counted. The pass still
reports PASS, the item still parks, and the parking record still names the
host leg as pending.

Measured 2026-10-25 on livespec-dev-tooling-jxepvj. Both records named the
sandbox image tag `python-rust-v1.133.0` as `release_tag`. That tag names an
image and is not a git tag of livespec-dev-tooling. The journal's
`proof-pointer` row showed `host_verified_record: None`. A corrected capture
fixed it: `release_tag: v1.133.0` (the git release that publishes that image
and contains the merge), with the image named under `installed_build`. A
replay naming the same build then closed the item.

So name the owning repository's git release tag, or its default-branch
commit, and put an image tag or a consumer's commit under `installed_build`.

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

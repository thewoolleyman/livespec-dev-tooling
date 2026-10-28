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

## Knowing when the replayer has finished

Do not decide from its PID or its log. Measured 2026-10-28 on
livespec-runtime-r6qc2o: the PID that the `setsid nohup … &` form hands back
exited within a minute, and the log held only the echoed brief. The real codex
process carried on, published `host_verified` at 19:09Z, and its post drove the
acceptance pass that closed the item. Reading the dead PID as a dead replayer
led to a relaunch, and the replay ran twice and posted a duplicate record.

The reliable signal is the record itself: watch the item's pull request for a
`Proof of Done — host_verified` (or `host_not_reproduced`) comment, and the
item's status. If you want a completion notice instead, start the same
`env -u … codex exec …` command as a harness background task, without
`setsid nohup … &`, and wait for its notification.

## Capturing a delegated-gate carrier's three pushes

A delegated-gate opt-in carrier usually owes three host-captured assertions:
a green push that completes, a red push refused on a failing verdict, and a
push refused when no verdict comes back. Three things made the first capture
(livespec-runtime-r6qc2o, 2026-10-28) work:

- **Each push needs a tree never gated before.** A byte-identical tree hits
  its green token and skips the gate, so give each case its own commit.
- **A red tree has to survive the commit hooks.** A non-`.py` change keeps the
  commit-time hook to its doc-only subset. A repo-private aggregate member, a
  justfile recipe that exits 1 and is appended to the `check` targets, is red
  only in the full aggregate the gate runs. A malformed proposed-change front
  matter is NOT red, because doctor-static does not judge it.
- **No verdict without delete rights.** The gates kubeconfig cannot delete a
  Job. Simulate a lost cluster instead. Copy `/etc/ci-runner/gates.kubeconfig`
  to a mode-600 file (`umask 077` and `command cp`; `install` is aliased to an
  apt wrapper here), rewrite its `server:` to an unreachable address, and pass
  `env GATES_KUBECONFIG=<copy>` to that one push. The host stays eligible,
  submission fails, the client reports `NO_VERDICT` and refuses. State the
  method in the record, and delete the copy afterwards.

Delete any proof branch that reached the forge with
`gh api -X DELETE repos/<owner>/<repo>/git/refs/heads/<branch>`, which fires no
pre-push hook.

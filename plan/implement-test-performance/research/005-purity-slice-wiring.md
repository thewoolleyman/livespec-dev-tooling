# 005 — Wiring a purity-declaration slice: two shapes every slice inherits

Recorded 2026-11-12 by the implement-test-performance plan seat, at
legacy-coordinator-agent's ruling (session 599f41e5, ~00:40Z). This note exists so
that any later purity-declaration slice inherits the two wiring shapes below. The
nine slices of livespec-dev-tooling-krc2yd were all filed before the shapes were
known.

## Background

livespec-dev-tooling-krc2yd (filed by the dispatch-payload-packaging seat,
2026-11-11 ~23:40Z) measured the problem. A matching delegated cluster green token
saved almost nothing at pre-push in nine fleet consumers, because their aggregate
members carried no purity declaration. livespec-dev-tooling
`SPECIFICATION/contracts.md` §"Delegated pre-push gate" counts an undeclared
member as world-reading, so the member still ran on the pushing host. That
included the full test suite under check-coverage.

The coordinator ruled it conformance, because the contract already requires
"Each member of a gate's check set carries its own purity declaration". It was cut
into one slice per repository, and krc2yd was closed as absorbed:

| Repository | Slice |
|---|---|
| livespec-orchestrator-beads-fabro | bd-ib-p2qt2j |
| livespec | livespec-kjpjq6 |
| livespec-console-beads-fabro | livespec-console-beads-fabro-2cix4o |
| livespec-overseer | overseer-kxqoda |
| livespec-driver-codex | livespec-driver-codex-xzlzvd |
| livespec-driver-claude | livespec-driver-claude-d5hgms |
| livespec-driver-pi | livespec-driver-pi-ee555c |
| livespec-orchestrator-git-jsonl | bd-gj-kiflbk |
| livespec-runtime | livespec-runtime-u6vrc5 |

Each slice's Definition of Done has four bullets:

1. `python -m livespec_dev_tooling.green_token undeclared` over every member of
   `just check` prints nothing and exits 0.
2. `just check` fails, naming the member, when a member carries no declaration.
3. Every member declared tree-pure passes in the factory sandbox, which holds no
   beads tenant credential and no forge token. Declarations are measured, never
   defaulted: a false-pure declaration is a false green.
4. Host-captured: a dev-host push of a tree with a matching cluster token runs only
   the members declared world-reading.

The Definition of Done said WHAT each bullet must make true, not HOW to wire it.
Two slices failed on HOW.

## Shape 1 — the refusal runs in the just check recipe body, adding no aggregate target

**What failed.** livespec-kjpjq6's second run armed livespec#3179, and its
required `check-metadata-batch` then failed with
`Failed targets: check-ci-matrix-completeness` (CI run 43122719982). The PR had
added the undeclared-member refusal (bullet 2) as a NEW `just check` target.
Every `just check` target needs a matching entry in the CI matrix under
`.github/workflows/`. A factory run cannot add that entry, because
`check-no-workflow-edits` refuses workflow edits. So the run could never go green.

**The shape that works.** livespec-driver-claude#1062 (merged, green) runs the
refusal INSIDE the `just check` recipe body, before any member is dispatched, over
the aggregate's own target list:

```bash
if ! bash dev-tooling/just/check-purity.sh "${targets[@]}"; then
    exit 1
fi
```

`just check` itself then fails naming the member, which satisfies bullet 2. No
aggregate target is added, so the CI matrix is unchanged. driver-claude's guard
also verifies that the `check-targets.txt` inventory and the aggregate list have
identical ordered membership.

## Shape 2 — each member is its own just invocation

**What failed.** livespec-driver-codex-xzlzvd failed `publish_draft@1`. Its push
ran `red_green_replay`, which crashed with a traceback (no refusal verdict) at
`msg_path.read_text` on a path that did not exist. The run's new
`dev-tooling/check-pre-push.sh` reran the world-reading members as:

```bash
exec just "${world_reading_targets[@]}"
```

`just a b c` passes `b` and `c` as ARGUMENTS to recipe `a` whenever `a` takes
parameters. `check-red-green-replay` takes `{1}` (its commit-message path at
commit-msg time), so the next member's NAME became that path.

**The shape that works.** Give each member its own invocation, and fail by naming
every member that failed:

```bash
failed=()
for t in "${world_reading_targets[@]}"; do
    just "$t" || failed+=("$t")
done
if (( ${#failed[@]} )); then
    printf 'FAILED targets: %s\n' "${failed[*]}" >&2
    exit 1
fi
```

Never pass several recipes on one `just` command line.

## Ordering rule (coordinator, 2026-11-11 ~23:00Z)

Bullet 2 arms a refusing check. That is safe only because the SAME commit first
makes the repository conform: every declaration (bullet 1), each measured true
(bullet 3). The sequence is adoption, then arming, inside one commit. A slice must
never land bullet 2 ahead of bullets 1 and 3, and must never arm the check in a
commit whose aggregate still has an undeclared member.

## Fleet sweep (rule K), 2026-11-12 ~00:38Z

I ran `git grep` over `origin/master` of every `/data/projects/livespec*` clone,
covering all tracked non-Markdown files including livespec's copier template. It
looked for any `just` invocation that takes a list. Results:

- **Shape 1 trap:** no fleet master has it. It exists only in kjpjq6's unmerged
  livespec#3179.
- **Shape 2 trap:** no fleet master has it. It exists only in xzlzvd's unmerged
  preserved tree. The one other match is
  `fleet-launch/wrappers/with-mi-homelab-key-and-livespec.sh:16`
  (`mise exec -- just "$@"`). That wrapper forwards a caller's single `just`
  command line by design.

There was nothing to file. Both items were released with rework riders that state
these shapes verbatim, and the four slices still running when the traps were found
(bd-ib-p2qt2j, overseer-kxqoda, bd-gj-kiflbk, livespec-console-beads-fabro-2cix4o)
carry both shapes as an item comment for any rework.

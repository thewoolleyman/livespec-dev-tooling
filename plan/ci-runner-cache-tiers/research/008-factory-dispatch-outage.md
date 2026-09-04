# 008 — The factory dispatch outage: fabro does not render `inputs.*` inside `run.prepare`

Written 2026-09-04, in the planning resume that tried to take the recorded
next action — dispatch `livespec-dev-tooling-npsqeu`, this plan's first
factory-routed child — and could not, because the dispatch died in setup
before any agent node ran. Every remaining piece of this plan is
factory-routed, so this note is about the thing now standing between the plan
and its own next step, not about the cache tiers.

## What happened

Run `01M1P5KM12JEKZJ81F1QB5P5NV` on
`https://hp-xubuntu.perch-rudd.ts.net:32276`, FAILED after 5 seconds, no
checkpointed diff, no agent node reached:

```text
Setup command failed (exit code 127):
set -- {{ inputs.prepare_toolchain_mise }}; test $# -eq 0 || "$@"
/bin/bash: line 1: {{: command not found
```

The first prepare command, `git fetch --unshallow --quiet`, carries no token
and ran. The second is the first templated one, and bash saw the two braces
as a command name.

## The isolated proof

The run dump alone would only support an inference, and one plausible reading
— that an EMPTY input value is what breaks the expansion — is wrong and worth
ruling out explicitly. So the behavior was reproduced away from this repo's
workflow entirely, in a throwaway three-node graph whose only content is one
templated prepare command and one templated node script reading the SAME
input:

```toml
[run.inputs]
probe_value = "RENDERED_DEFAULT"

[[run.prepare.steps]]
script = "echo PREPARE_TOKEN_SAW: {{ inputs.probe_value }}"
```

```text
probe [ shape=parallelogram script="echo NODE_TOKEN_SAW: {{ inputs.probe_value }}" ]
```

Created with `fabro create probe.toml --input probe_value=RENDERED_FROM_FLAG`
and never started, then read back from the persisted spec:

| Where the token sits | What the persisted spec holds |
|---|---|
| graph node attribute | `NODE_TOKEN_SAW: RENDERED_FROM_FLAG` |
| `run.prepare` command | `echo PREPARE_TOKEN_SAW: {{ inputs.probe_value }}` |

One run, one input, one value, two sites, two different answers. fabro
0.254.0 renders `inputs.*` in graph node attributes at run-create time and
does NOT render them in `run.prepare` commands. An empty value is not the
trigger; neither is anything about this repository. The probe run was
force-removed after the read.

## Why the real dispatch confirms the same thing

`spec.settings.run.inputs` on the failed run carries every contract input the
Dispatcher resolved — `prepare_toolchain_mise=''`,
`prepare_toolchain_lefthook=''`, `conformance_hook_install=''`,
`conformance_verify_commit_refuse_hook=''`,
`conformance_verify_plugin_resolution=''`,
`sandbox_exempt_marker='livespec.sandboxExempt'`, `default_branch='master'`,
`sandbox_check_suite='mise exec -- just check'` — so the host side did its
job. `spec.settings.run.prepare.commands` still hold the raw token text. The
non-empty `git config {{ inputs.sandbox_exempt_marker }} true` two commands
later is equally unexpanded, which is the same empty-value rebuttal the probe
makes in isolation.

## When this started, and what it does not mean

The templated prepare steps landed in `livespec-orchestrator-beads-fabro`
commit `39526e5c` on 2026-08-31 ("feat(payload): template the
implement-work-item payload from the resolved integration contract",
`bd-ib-b7xpzl`), and that commit is in the release the installed plugin runs,
v0.124.2 / build `af7bf8e6acf1`.

Read the dispatch journal carefully rather than generalising. The last two
dispatches in this repo before today, both `livespec-dev-tooling-ys2i` on
2026-08-30, ran `Setup: 24 commands (24s)` and reached the Implement node;
they failed later and for unrelated reasons (an ACP turn timeout, then a
blocked Green amend), on a 14-node/25-edge workflow. Today's run used the
13-node/22-edge released workflow. So the honest claim is not "every dispatch
since 2026-08-31 failed" — it is that **no dispatch had exercised the
templated payload until this one, and the first one that did failed
deterministically and for reasons independent of the item it carried.**

## Why the static gate cannot see it

`check-seam-equivalence` asserts, in both directions, that the `[run.inputs]`
declarations, the tokens the payload references, and the Dispatcher's rendered
inputs are identical, and that every token sits where the pinned engine
renders it. The first three agree. The false premise is the fourth: the engine
does not render this site. A gate that compares three host-side artifacts to
each other cannot discover that the fourth party never agreed to the contract.

## The fix, and why it is small

The Dispatcher ALREADY materializes an uncommitted, mode-600, per-dispatch
overlay of `workflow.toml` and rewrites it in three ways: the graph path is
absolutised, one sibling-clone prepare step is appended per fleet member, and
the credential environment table is appended. Substituting the resolved
contract values into the prepare commands is a fourth rewrite in the same
place, on the same host, against the same already-resolved
`ResolvedIntegrationContract`. It needs no engine change and no new seam. The
alternative — asking the engine to render `run.prepare` — is a fabro change
with a version pin behind it, and the probe above says there is nothing to
wait for today.

Whichever way it lands, the gate needs a companion check that fails when a
`{{ ... }}` token survives into a materialized overlay's prepare commands,
because that is the class of defect the static equivalence check is
structurally unable to catch.

## Adjacent findings, recorded so they are not rediscovered

- This repository's `.livespec.jsonc` declares no `dispatcher` key at all, so
  the dispatch warned that three conformance premises — `hook_install`,
  `verify_commit_refuse_hook`, `verify_plugin_resolution` — are undeclared and
  will be SKIPPED in the sandbox. Declaring each explicitly as `no_op` puts
  the choice on the record and silences the warning. It does not fix the
  outage: the tokens are unexpanded whether their values are empty or not.
- The dispatch pulled `livespec-fabro-sandbox:python-agent-v1.40.0`, the
  Python-only layer, because this repo commits no
  `.fabro/workflows/implement-work-item/workflow.toml` of its own to pin the
  `python-rust` layer. `npsqeu`'s narrowed half needs no cargo, so this did
  not bite here, but a Rust-touching item dispatched from this repo would.
- The dispatch was attributed `unattributed:unknown-user@vmi3006760` with
  `invoker_source: fallback`, as the 2026-08-30 runs also were.

## What this changed on the ledger

`livespec-dev-tooling-npsqeu` was narrowed to this repository's half before
the dispatch — the cross-repo receiver-allowlist and sandbox-resolution work,
and the end-to-end `get_span_details` verification that depends on it, are no
longer in its acceptance and need a carrier filed in
`livespec-orchestrator-beads-fabro`'s own ledger. After the failure the item
was returned to `blocked` with `blocked-reason:infra-external` and its
assignee cleared. Its two newest comments carry the narrowing rationale and
the failure forensics. Do not re-dispatch it as-is; the next attempt fails
identically, five seconds in, at the same prepare command.

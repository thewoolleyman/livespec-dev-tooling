# Handoff — shell-logic-hardening (livespec-dev-tooling)

**Thread:** `plan/shell-logic-hardening/` · **Ledger anchor:** the EXISTING
epic `livespec-dev-tooling-9j8` (`livespec-dev-tooling` beads tenant).
This thread carries the remediation of the fleet-wide shell-logic audit:
moving substantive logic out of untested shell / heredoc-Python into the
test + pyright + coverage harness, behind mechanical gates (shellcheck
wiring, a logic-in-shell ceiling check, behavioral tests for
fleet-distributed shell).

> Status is **derived from the ledger**, never stored in this file. To read
> it (epic + all children, with their current states):
>
> ```bash
> source /data/projects/1password-env-wrapper/with-livespec-env.sh \
>   bd -C /data/projects/livespec-dev-tooling show livespec-dev-tooling-9j8
> ```
>
> (the wrapper injects the tenant password; never echo it). A trailing
> `auto-backup failed … command denied` warning is correct-by-design
> tenant confinement, not an error.

## Read first (in order)

1. `plan/shell-logic-hardening/research/findings.md` — the consolidated
   audit record: per-repo verdicts, the maintainer-decided RULE + GATES
   policy (2026-06-30), right-pattern exemplars, the ranked concern list,
   and the §"Ledger anchor" table mapping each concern to its ledger id.

That single document is the design of record for this thread. The epic
description in the ledger restates the RULE, GATES, and rationale, so the
`bd show` above plus the findings doc together give a fresh session the
complete picture.

## What the thread is

The audit (completed 2026-06-30) found no product-logic-in-shell dodge,
but did find substantive logic living outside the tested harness in shell
scripts and `python -c` / heredoc-Python. The maintainer decided a RULE
(substantive logic must live in a tested, type-checked, importable module
regardless of invocation; shell/heredocs are thin glue only) plus
mechanical GATES, not a blanket shell ban. The dev-tooling-owned
remediation is layered as epic `livespec-dev-tooling-9j8` with children
`livespec-dev-tooling-9j8.1` through `livespec-dev-tooling-9j8.8`;
cross-repo concerns are filed in their own tenants with prose
cross-references to this epic (never typed cross-tenant `depends_on`).

## Next action (one path)

Run the status-read command above, then dispatch/implement the ready
`livespec-dev-tooling-9j8` children (`9j8.1` is the FIRST READY per the
epic description; the epic notes it still needs grooming into final
ready / dependency-layered slices — groom first if `bd show` reveals no
ready child). Implementation of each child goes through the normal
factory path (`/livespec-orchestrator-beads-fabro:implement <id>` in its
own worktree, Red→Green, `just check` green, PR, merge, close the child
in the ledger).

## Resume command

```
/livespec-orchestrator-beads-fabro:plan shell-logic-hardening
```

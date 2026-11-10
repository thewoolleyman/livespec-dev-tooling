---
topic: check-runner-coverage-dir-cleanup
author: claude-opus-5-5
created_at: 2026-11-10T00:30:10Z
---

## Proposal: Check runners remove their coverage directories when terminated

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add one paragraph to §"Enforcement-suite invocation": a check runner that isolates coverage data removes every coverage-namespace temp directory it created before it exits, and on SIGTERM or SIGHUP removes them and exits non-zero. A scenario states the observable behaviour.

### Motivation

Measured on the dev host vmi3006760 on 2026-11-09, by plan dev-host-disk-retention (epic livespec-dev-tooling-qgwxo4) at legacy-coordinator-agent's request.

- The 48G /tmp tmpfs was at 79%. It held 122 `covns-full-tree-*` and 16 `covns-incremental-*` directories, the oldest from 2026-10-19 and about 3.0 GiB in total. They were reclaimed by hand. livespec-dev-tooling-8o8e.16 recorded the same leak back to 2026-07-19.
- `build_namespace_dirs` in `livespec_dev_tooling/_dispatcher_coverage_namespaces.py` creates them, and `isolated_environments()` removes them in a `finally`. None of the three entry points installs a SIGTERM or SIGHUP handler: `parallel_check_dispatcher.py`, `incident_local_gates.py` and `incident_ci_entry.py`.
- Python's default action for those signals ends the process without unwinding, so every killed run leaves its directory behind. The gate runner's stall timeout sends TERM to the group, a lefthook hook's client hears SIGHUP, and harness and janitor kills do the same.
- A full /tmp breaks Bash capture, heredocs, gates and factory preflights on every seat. The same runners run in gate pods and factory pods.

No clause of the spec states this lifecycle. The pre-dispatch screen of livespec-dev-tooling-8o8e.16, the item that owns the fix, refused it on 2026-11-10 at 00:28:07Z for that reason: its only reference, `## Detached gate runner`, does not govern the dispatcher's coverage-namespace directories.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md` §"Enforcement-suite invocation", insert this paragraph immediately after the paragraph that begins "The `just` target that runs the whole test suite with coverage":

> **Check runners leave no coverage directories behind.** A check runner this repository ships that isolates coverage data creates one coverage-namespace directory under the system temp directory for each coverage namespace its run uses. These runners are the parallel check dispatcher behind `just check`, and the expedited incident paths' local-gate runner and CI entry point. Before it exits, a runner MUST remove every such directory it created, whether its targets pass or fail. When it receives SIGTERM or SIGHUP, it MUST remove every such directory it created and then exit with a non-zero status. A terminated run then never reads as a pass, and it leaves no coverage directory in the temp directory of the dev host, a gate pod or a factory pod. A runner killed by SIGKILL is outside this rule, because no process can act on that signal.

In `SPECIFICATION/scenarios.md`, immediately after `## Scenario: a check aggregate member with no purity declaration fails the aggregate`, add:

```
## Scenario: a check runner terminated by SIGTERM or SIGHUP removes its coverage directories and exits non-zero

Given a check runner whose selected targets include a coverage-touching target, with its temp directory pointed at an empty directory

When the runner receives SIGTERM, or SIGHUP, while that target is running

Then the runner MUST exit with a non-zero status

And the temp directory MUST hold no coverage-namespace directory the runner created
```

The new H2 scenario heading MUST be registered in `tests/heading-coverage.json` in the revise commit that accepts this proposal, owned by livespec-dev-tooling-8o8e.16.

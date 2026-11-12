---
topic: gate-job-only-tests
author: claude-opus-5-5
created_at: 2026-11-12T07:03:11Z
---

## Proposal: A repository declares gate-Job-only test modules, and the agent guard refuses their foreground runs whatever the worker count

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a gate_job_only_tests key (path globs) to [tool.livespec_dev_tooling]; under the full-suite rule's two conditions the agent guard refuses a foreground pytest naming a matching module whatever its worker count, naming the gate-start form; this repository declares its ansible-playbook-driving modules. Amend What is not refused accordingly, and add one scenario.

### Motivation

Measured 2026-11-12 ~05:16-05:35Z on the dev host (vmi3006760): CPU PSI avg60 was about 70, and the dispatcher's pre-launch passes took 20-30 min from LAUNCH to LISTED. An agent session's targeted foreground run of `tests/livespec_dev_tooling/test_apparmor_profile_role.py` at -n 6 drove a real `ansible-playbook` per test, at 150-175% CPU each. A later run of the same module at -n 2 ran for 231 s. The guard's ratified full-suite rule refuses only a pytest with no explicit path or with `-n`, so the same module run with explicit paths and no `-n` is allowed by design and still puts ansible load on the host. livespec-dev-tooling-kkzjvx fixes the separate conformance bug (a `~` or variable `cd` target slipped past the `-n` rule). legacy-coordinator-agent asked for this rule (2026-11-12 ~07:0xZ): a module that drives ansible-playbook goes to a gate Job whatever the worker count. The guard decides from command text, so the rule needs a declared, mechanical criterion; a per-repository glob list is cheap to read and needs no test import. Fleet scope: livespec-dev-tooling has 39 ansible-playbook-driving test files (2026-11-12); livespec, livespec-orchestrator-beads-fabro, livespec-overseer and homelab have none. The key is optional, so other repositories are unaffected until they declare it.

### Proposed Changes

In SPECIFICATION/contracts.md, section "## Agent-session gate-command guard", insert this bullet directly after the "**Foreground full-suite pytest.**" bullet:

- **Gate-Job-only test modules.** A repository MAY declare `gate_job_only_tests` in its `[tool.livespec_dev_tooling]` table: an array of repository-relative path globs naming test modules that must never run in an agent session's foreground, such as modules whose tests each drive `ansible-playbook`. Under the same two conditions as **Foreground full-suite pytest** (the target repository has `delegated_gate = true` and the session's user can read the gates kubeconfig), the guard MUST refuse a foreground pytest invocation that names a file, directory or node id matching one of those globs, whatever worker count it asks for, and MUST name the same one-call detached form. A named directory matches when it contains a matching module. An absent key, an empty array, or a value that is not an array of strings declares none, and the guard then judges the invocation by the full-suite rule alone. This repository MUST declare its `ansible-playbook`-driving test modules in that key. A check this repository runs MUST fail when a test module that invokes `ansible-playbook` matches no declared `gate_job_only_tests` glob, naming the module.

In the same section's "**What is not refused.**" bullet, change "a foreground pytest that names explicit test files, directories or node ids and does not pass `-n` or `--numprocesses`" to "a foreground pytest that names explicit test files, directories or node ids, matches no declared `gate_job_only_tests` glob, and does not pass `-n` or `--numprocesses`".

In SPECIFICATION/scenarios.md, add this scenario directly after "## Scenario: an agent session's foreground full-suite pytest on a delegating host is refused and names the gate-start form" (heading preceded and followed by a blank line, matching the surrounding scenarios):

## Scenario: an agent session's foreground pytest of a gate-Job-only test module is refused whatever its worker count

Given a repository with `delegated_gate = true` whose `[tool.livespec_dev_tooling]` table declares `gate_job_only_tests` matching `tests/livespec_dev_tooling/test_apparmor_profile_role.py`

And an agent session on a host whose user can read the gates kubeconfig

When the session runs a foreground pytest invocation that names that file and passes no `-n`

Then the guard MUST refuse the call and name the one-call `gate-start` form

And the same invocation dispatched through `gate-start` MUST NOT be refused

The revise that accepts this MUST add a `tests/heading-coverage.json` row for the new scenario in the same commit, as a spec-first `"test": "TODO"` row at the integration tier owned by the implementing work item the plan seat files after ratification, and regenerate the heading-coverage debt register.

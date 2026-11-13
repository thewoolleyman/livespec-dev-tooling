---
topic: pressure-telemetry-sh-and-apply
author: claude:kubernetes-observability-seat-230b17
created_at: 2026-11-13T18:18:25Z
---

## Proposal: No credential in a process's argument vector

### Target specification files

- SPECIFICATION/constraints.md
- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add one repository-wide rule: no script, unit, playbook task or workflow step this repository ships or runs passes a credential in the argument vector of a process it starts. The credential goes through stdin, an owner-only file, or the child's environment. Name the rule from §"Execution-target pressure telemetry" so the pressure emitter's Honeycomb post is plainly under it, and add a scenario that proves it with a recording stand-in for the child process. The rule is placed in `constraints.md` because it also governs code this repository ships for other fleet repositories to run, such as the CI run-telemetry exporter, where a consumer can observe a violation.

### Motivation

Found 2026-11-13 by the kubernetes-observability seat and routed spec-first by legacy-coordinator-agent (work item livespec-dev-tooling-d5k6qc). `ansible/roles/pressure_telemetry/files/pressure-telemetry.sh` posts PSI with `curl -H "X-Honeycomb-Team: ${HONEYCOMB_INGEST_KEY_LIVESPEC}"`, so the expanded ingest key sits in curl's argv for the life of each post. Any local user can read it from `/proc/<pid>/cmdline` or `ps -ef`. The role runs on a timer on every dev-host and ci-pool host, including vmi3006760, so this is a live exposure. `ci-runner/observability/triggers/apply-triggers.sh` does the same with the Honeycomb configuration key, which can write triggers, boards and recipients. The CI run-telemetry exporter this repository ships (`livespec_dev_tooling/ci_run_telemetry.py`, run by `.github/scripts/export-ci-telemetry.sh`) already conforms: it sets the header in-process and starts no child process with the key. But ten fleet members still run an older local copy of `export-ci-telemetry.sh` that passes `-H "x-honeycomb-team: $KEY"` to curl: livespec, its `templates/orchestrator-plugin`, livespec-overseer, livespec-orchestrator-beads-fabro, livespec-console-beads-fabro, livespec-runtime, livespec-driver-codex, livespec-driver-claude, livespec-driver-pi and livespec-orchestrator-git-jsonl. The **One CI run-telemetry exporter** paragraph of §"Runner-pool node telemetry" already requires each member to run the shipped module through its pin, with no copy, so each one is cleared by adopting that clause through its ordinary pin bump. This rule adds no new obligation there. No ratified clause forbids this: the spec-change tier record for d5k6qc (spec v212) found the core behaviour unstated, so the rule has to be ratified before the fix can be admitted. A process's environment, unlike its argv, is readable only by the same user and by root (`/proc/<pid>/environ` is mode 0400), so the environment is an acceptable channel and argv is not. Hits of the same shape in other repositories (livespec-console-beads-fabro, livespec-orchestrator-beads-fabro, dolt-server, vps-info) are owned by sibling items in those repositories and are outside this spec target.

### Proposed Changes

1. `constraints.md`: add a new H2 section, placed after §"CLI shape":

```markdown
## No credential in a process's argument vector

No script, systemd unit, Ansible task or template, `just` recipe, or workflow step that this repository ships or runs MAY place a credential in the argument vector of a process it starts. That includes code this repository ships for other fleet repositories to run, such as the CI run-telemetry exporter of the **One CI run-telemetry exporter** paragraph of `non-functional-requirements.md` §"Runner-pool node telemetry". A credential is any API key, ingest or configuration key, token, password or private key, and any value expanded from a variable or secret that holds one. The rule covers an HTTP header carrying a credential, such as `curl -H "X-Honeycomb-Team: <key>"`, and a credential passed as a flag value or a positional argument. A credential MUST instead reach the child process through its standard input (for `curl`, `-H @-` or `-K -`), through a file readable only by its owner (mode `0600` or stricter) that is removed when the parent exits, or through the child's environment. A shipped script's tests MUST run it with a recording stand-in for each child process that takes a credential, and MUST fail when any recorded argument vector contains the credential's value. This section is spec-first: `ansible/roles/pressure_telemetry/files/pressure-telemetry.sh` and `ci-runner/observability/triggers/apply-triggers.sh` still pass a Honeycomb key in curl's argv, and work item livespec-dev-tooling-d5k6qc owns the change.
```

2. `non-functional-requirements.md` §"Execution-target pressure telemetry", in the **Pressure stall information on every execution target** paragraph, append: "The emitter's post to the Honeycomb `livespec` environment MUST pass its ingest key as `constraints.md` §\"No credential in a process's argument vector\" requires, so the key MUST NOT appear in the argument vector of any process the emitter starts."

3. `scenarios.md`: add a scenario:

```markdown
## Scenario: a shipped script hands its Honeycomb key to curl without placing it in curl's argument vector

Given `pressure-telemetry.sh` runs with `HONEYCOMB_INGEST_KEY_LIVESPEC` set to a known test value, and a recording stand-in for `curl` that records its argument vector, its standard input and every file a `-K` or `-H @` argument names

When the script posts its PSI datapoints

Then no recorded argument vector MUST contain the test value

And the stand-in MUST have received an `X-Honeycomb-Team` header whose value equals the test value, through its standard input or an owner-only file

And the same MUST hold for `ci-runner/observability/triggers/apply-triggers.sh` with its Honeycomb configuration key
```

The revise that accepts this proposal MUST add `tests/heading-coverage.json` entries for both new H2 headings in the same commit.

---
topic: state-writing-cli-requires-explicit-state-path
author: claude-opus-5-5
created_at: 2026-11-12T04:08:15Z
---

## Proposal: A state-writing CLI requires its state-path flag and never defaults to live host state

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add a Testing approach bullet: a livespec_dev_tooling command-line entry point that writes host state takes each state location only from an explicit flag, refuses without it (exit non-zero, naming the flag, touching nothing), and every committed invoker passes the flag, with the test suite failing on an invoker that omits it. Add two scenarios, one for the refusal and one for the committed-invoker check.

### Motivation

livespec-dev-tooling-6cgj2e (a child of plan dev-host-test-gate-load) removes a hazard measured on the dev host: `test_the_host_cli_reports_the_nodeids_it_files` called `flake_retry_filer.main` with no `--state-dir`, the argparse default /var/lib/livespec/flake-retry-filer applied, and the test touched the live reader's `last-successful-pass` marker, so a dead reader would have read as fresh. The existing `tests_host_path_free` check cannot see this, because an omitted flag names no path literal. A re-sweep of master (recorded on 6cgj2e) found the same write-default on flake_retry_filer --state-dir, docker-engine-guard and its preflight --state-root (/var/lib/docker-engine-guard), and docker-engine-guard --runtime-root (/run/docker-engine-guard). 6cgj2e's launch-time Definition-of-Done preflight refused it at 2026-11-12T03:57:18Z because no ratified heading states the behaviour: §"Testing approach" only names the host-side reader, and §"Docker engine install guard" only says where durable state lives. This proposal ratifies the rule so 6cgj2e can reference it. legacy-coordinator-agent ruled GO on this wording, including the committed-invoker half and its scenario, at about 04:05Z on 2026-11-12. §"Docker engine install guard"'s statement that durable state lives under /var/lib/docker-engine-guard stays true: the committed invoker passes that path explicitly.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md, section "## Testing approach", insert this bullet directly after the "**Environment-independent test coverage.**" bullet:

- **Host-state isolation of CLIs.** A command-line entry point under `livespec_dev_tooling/` whose run writes host state, meaning files or directories outside the caller's working tree that a host service or timer also reads, such as a state directory, a state root or a runtime root, MUST take each such location only from an explicit flag and MUST NOT default it to a live host path. Invoked without that flag, it MUST exit non-zero with a message naming the flag, and MUST create, modify or touch nothing on the host. Every committed systemd unit, ansible template or script that invokes such an entry point MUST pass each of those flags explicitly, and the repository's test suite MUST fail, naming the invoker file and the missing flag, when one does not. A path the entry point only reads, and a shared rendezvous location that every caller is meant to use, such as a host-wide lock or slot directory, are outside this rule.

In SPECIFICATION/scenarios.md, add these two scenarios directly after "## Scenario: a CI job that re-ran no test publishes no flake-retry artifact" (each heading preceded and followed by a blank line, matching the surrounding scenarios):

## Scenario: a state-writing CLI invoked without its state-path flag refuses and touches no host state

Given a command-line entry point under `livespec_dev_tooling/` whose run writes host state at a location named by a flag, such as the flake-retry filer's `--state-dir` or the Docker engine install guard's `--state-root`

When it is invoked without that flag

Then it MUST exit non-zero with a message naming the flag

And it MUST NOT create, modify or touch anything under the host path it writes when a committed invoker runs it

## Scenario: a committed invoker that omits a state-writing CLI's state-path flag fails the test suite

Given a committed systemd unit, ansible template or script that invokes a command-line entry point under `livespec_dev_tooling/` whose run writes host state

And that invoker does not pass one of the entry point's state-location flags

When the repository's test suite runs

Then it MUST fail with a message naming the invoker file and the missing flag

The revise that accepts this MUST add a `tests/heading-coverage.json` row for each new scenario in the same commit, as a spec-first `"test": "TODO"` row at the integration tier owned by `"work_item": "livespec-dev-tooling-6cgj2e"`, and regenerate the heading-coverage debt register.

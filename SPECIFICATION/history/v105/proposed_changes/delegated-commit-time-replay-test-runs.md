---
topic: delegated-commit-time-replay-test-runs
author: claude-opus-5-5
created_at: 2026-11-01T13:26:52Z
---

## Proposal: The gate client delegates the commit-msg replay gate's test runs against the staged tree

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add `## Delegated commit-time replay test runs` to contracts.md, directly after `## Delegated pre-push gate`. It states, for consuming repositories, the client side of the commit-time delegation livespec ratified in v234 (MODIFY): its own opt-in key, which hosts delegate, staged-tree identity, the Red/Green judgement and trailers kept on the committing host, trailers that name the gate Job and the staged tree, a local fallback on an absent verdict, and the pre-commit aggregate left undelegated.

### Motivation

livespec v234 ratified delegating the commit-msg replay gate's test runs (livespec scenarios.md `## Delegated commit-time replay test runs`), but this repository, which ships the gate client and the replay gate, carries no consumer-facing contract for it. Today only the pre-push gate delegates, so every Red, Green and suite-green test run of every commit runs on the committing host. Measured on the dev host vmi3006760 (18 CPUs) on 2026-11-01: sar showed 8-21% idle with 33-47% system time in every 10-minute bucket from 09:00Z to 12:40Z, while commit-time suites and janitors ran there. One commit's suite-green leg re-ran the whole suite after a 23-minute green pre-commit, then failed on load-sensitive tests (rc 1 at 2084 s) or timed out at 2400 s. Work item livespec-dev-tooling-sewnfp implements the client and is held until this heading exists. The modified livespec decision differs from the original proposal in two ways this contract must carry: an absent verdict falls back to a real local run instead of refusing the commit, and the trailers identify the executor run and the staged tree.

### Proposed Changes

Insert into `contracts.md`, immediately after the `## Delegated pre-push gate` section and before `## Agent-session gate-command guard`:

```markdown
## Delegated commit-time replay test runs

A consuming repository MAY run the test runs that the commit-msg replay gate (`red_green_replay`) makes, for its Red leg, its Green leg and its suite-green leg, as a Kubernetes Job. The gate client submits that Job to the same `gates` namespace the pre-push delegation uses, instead of running the tests on the committing host. This section is the consumer-facing contract of that delegation as this repository ships it, and it is the client side of livespec's `non-functional-requirements.md` **Delegated commit-time gate execution**. Delegation changes WHERE a replay test run executes. It MUST NOT change WHAT the replay gate verifies, which tests a leg selects, or how it judges them.

- **Opt-in.** Commit-time delegation is switched on by `delegated_commit_tests = true` in the consumer's `[tool.livespec_dev_tooling]` table. The key is separate from `delegated_gate`, so a repository MAY delegate its pre-push gate, its commit-time replay test runs, both, or neither. It is read by its own loader, like `delegated_gate`, and is not a role key. Only the literal boolean `true` enables it. An absent key, `false`, a value of another type, or an unreadable `pyproject.toml` all leave the replay test runs on the committing host.
- **Host eligibility.** With the key switched on, a commit delegates only when the committing user can read the gates kubeconfig on that host, exactly as §"Delegated pre-push gate" decides for a push. A host that holds no gates credential, such as a factory sandbox, runs the replay test runs locally. It MUST say in the hook's output that it gated locally.
- **The staged tree.** A delegated replay test run MUST execute against the tree that `git write-tree` names for the index when the hook runs, not the tree of `HEAD` and not the working directory. For a Green amend, that tree is the amended commit's tree as staged. The gate client MUST publish that tree to the cluster's gate mirror the same way it publishes a pushed tree. The committing host MUST verify that the Job's reported tree hash equals the staged tree hash before it honours the outcome. An outcome reported for any other tree is an absent verdict.
- **What the Job runs.** The gate Job MUST run the same pytest invocation the replay gate would run locally for that leg, with the same selected test paths, and nothing else. A Red leg runs its staged tests. A Green leg runs the Red test. A suite-green leg runs at the scope the replay gate selected, either the staged test modules or the full suite. The Job MUST report the run's outcome, `passed` or `failed`, together with the complete pytest output.
- **Judgement and trailers stay on the committing host.** The committing host MUST judge each leg from the reported outcome exactly as it judges a local run: a Red leg needs a failing test, and a Green leg needs the same byte-identical test now passing. It MUST compute every output checksum from the reported output. Every trailer set recorded from a delegated run MUST also carry the gate Job's name and the staged tree hash, so that the commit names the run that produced its verdict.
- **Absent verdict.** A verdict is absent when the API server is unreachable, the credential cannot be refreshed, the Job cannot be submitted, the Job is lost or times out, or the reported tree does not match. In each case the committing host MUST run that leg's tests itself. It MUST record that leg's trailers only from that local run, never from the absent verdict, and MUST say that it gated locally. A commit MUST NOT be refused because the cluster returned no verdict. This departs from §"Delegated pre-push gate" for commits only: a push without a verdict is still refused.
- **The pre-commit aggregate is not delegated.** `just check-pre-commit` keeps running on the committing host whether or not this key is set.
- **Credential use and installation.** Cluster commands go through `with-gates-kubeconfig` against the gates kubeconfig that the `gates_kubeconfig` role installs, as §"Delegated pre-push gate" states. This delegation adds no credential.
```

Append to `scenarios.md`, after `## Scenario: an idle detached gate run and an idle waiter spawn no per-tick process`:

```markdown
## Scenario: an opted-in commit from a credentialed host runs its replay tests against the staged tree

Given a repository with `delegated_commit_tests = true`
And a committing host whose user can read the gates kubeconfig
And a working directory whose unstaged edits differ from the index
When the developer makes a Red commit
Then the gate Job MUST run the Red leg's staged tests against the tree `git write-tree` names for the index
And the committing host MUST verify that tree hash before honouring the reported outcome
And the committing host MUST run no pytest for that leg

## Scenario: a delegated replay leg's trailers name the gate Job and the staged tree

Given a repository with `delegated_commit_tests = true`
And a committing host whose user can read the gates kubeconfig
When the gate Job reports the Red leg's test as failed, with its output
Then the committing host MUST judge the Red expectation from that reported outcome
And the TDD-Red trailers MUST record the output checksum computed from the reported output
And the TDD-Red trailers MUST name the gate Job and the staged tree hash

## Scenario: a delegated replay leg with no verdict falls back to a local run

Given a repository with `delegated_commit_tests = true`
And a committing host whose user can read the gates kubeconfig
When the developer makes a Red commit and the gate Job returns no verdict
Then the committing host MUST run the Red leg's staged tests itself
And the TDD-Red trailers MUST be recorded from that local run, not from the absent verdict
And the hook MUST say that it gated locally
And the commit MUST NOT be refused because the cluster returned no verdict

## Scenario: a commit from a host without the gates credential runs its replay tests locally and says so

Given a repository with `delegated_commit_tests = true`
And a committing host whose user cannot read the gates kubeconfig
When the developer commits
Then the replay gate's test runs MUST execute on the committing host
And the hook MUST say that it gated locally
```

The four scenarios above are added to `scenarios.md` beside the existing delegated-gate scenarios. Each new H2, the contracts.md heading and the four scenario headings, is bound in `tests/heading-coverage.json` by the accepting revise as a spec-first `TODO` row. Each row's reason names the integration tier and work item livespec-dev-tooling-sewnfp, and each row is registered in the heading-coverage debt register.

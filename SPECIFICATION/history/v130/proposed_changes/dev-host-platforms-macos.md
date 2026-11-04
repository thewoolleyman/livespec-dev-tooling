---
topic: dev-host-platforms-macos
author: claude-opus-5-5
created_at: 2026-11-04T14:06:20Z
---

## Proposal: Developer hosts are Linux and macOS arm64, with named toolchain sources and ledger reach

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add a `## Developer host platforms` section to `non-functional-requirements.md`, placed directly after §"Local gate concurrency limit". It names the two developer-host platforms, Linux and macOS arm64, and requires the code that runs on a developer host to run on both. It names where each host toolchain prerequisite comes from: bare `python3` satisfying `requires-python` (on macOS from uv, never from Homebrew), bash 4 or later, and `node` from mise. It states how a host without the Dolt server reaches the ledger tenant: an approved SSH local forward onto the committed loopback address, with no config change, no `bd init` and no local store. One scenario covers ledger reach.

### Motivation

Plan `homelab-k8s-worker-nodes` (epic livespec-dev-tooling-ko26ez), research note 001 §"Development bootstrap prerequisites" and Stage 0, moves implementation onto a 2026 MacBook Air (macOS arm64). Bootstrapping that Mac measured the following. The specification names no developer-host platform, so nothing says that a hook or gate must run on macOS. `.claude/settings.json` runs `.claude/hooks/livespec_footgun_guard.py` through bare `python3`, and macOS's system `python3` is older than the `requires-python = ">=3.10.16"` floor. The maintainer ruled Homebrew Python wrong for this; uv's `uv python install 3.10.16 --default`, which links `python3` into `~/.local/bin`, is the source. `dev-tooling/gate-run.sh` uses `mapfile`, which macOS's bash 3.2 does not have. Without `node` on PATH, pyright-python falls back to nodeenv, and that fallback crashes. The repository tools uv, just and lefthook already come from `.mise.toml` (§"Toolchain pins"), so this proposal does not change those pins. AGENTS.md §"Beads runtime prerequisites" fixes the tenant at loopback `127.0.0.1:3307`, and a Mac has no Dolt server. The working route was a LaunchAgent running `ssh -N -L 3307:127.0.0.1:3307 vps`. The 1Password environment wrapper supplies the tenant credential, and it supports Darwin through the Keychain. Code that runs only on Linux pool nodes (`ci-runner/`, `ansible/`) is deliberately out of scope. Requirements are stated as rulings only where these measurements and the maintainer's Homebrew ruling decide them. Nothing here is a SHOULD, because no open design choice arose in this half.

### Proposed Changes

Insert a new H2 section into `non-functional-requirements.md` directly after §"Local gate concurrency limit" (before §"Commit and merge discipline"), reading:

```markdown
## Developer host platforms

**Platforms.** A developer host is a machine on which a contributor or an agent session edits, commits and pushes this repository. Developer hosts are Linux hosts and macOS hosts on arm64. Code of this repository that runs on a developer host — the repository's git hooks and agent-session hooks (`.claude/hooks/`), the commit and pre-push gates, the detached gate runner, and `just bootstrap` — MUST run on both platforms. On macOS, a gate member that depends on a Linux-only facility, such as `/proc` or `os.sched_getaffinity`, MUST NOT pass vacuously or hang. Such a host obtains those members' verdicts through the delegated route that **Gates on a non-Linux host** below requires. Code that runs only on Linux runner-pool or factory nodes, which is the `ci-runner/` and `ansible/` trees, is outside this section.

**Host toolchain sources.** A developer host MUST supply these prerequisites on `PATH`, in addition to the repository tools §"Toolchain pins" pins in `.mise.toml` (uv, just, lefthook):

- A bare `python3` whose version satisfies `pyproject.toml`'s `requires-python`. Repository hooks, such as `.claude/hooks/livespec_footgun_guard.py`, run through bare `python3` rather than through uv. On macOS that interpreter MUST be provided by uv, through `uv python install <version> --default`, which links `python3` into `~/.local/bin`. It MUST NOT be provided by an OS package manager such as Homebrew.
- bash 4 or later, because the detached gate runner uses `mapfile`. macOS ships bash 3.2, which therefore does not satisfy this.
- `node`, provided by mise, so that pyright runs on the host's `node`. pyright-python's nodeenv fallback, which runs when `node` is absent, MUST NOT be relied on.

**Ledger reach.** A developer host that does not run the family Dolt server MUST reach this repository's ledger tenant at the committed loopback address `127.0.0.1:3307` through an approved SSH local forward to the server host's `127.0.0.1:3307`. On macOS this is a per-user LaunchAgent that runs `ssh -N -L 3307:127.0.0.1:3307 vps`. The committed `.beads/config.yaml` MUST NOT be changed to reach the tenant. A developer host MUST NOT run `bd init`, and MUST NOT create or answer from a local beads store. The tenant credential MUST come through the 1Password environment wrapper, `/usr/local/bin/with-livespec-env.sh`, which on macOS reads its token through the Keychain. It MUST NOT come from a credential file copied from another host.
```

Append to `scenarios.md`:

```markdown
## Scenario: a macOS developer host reads the ledger tenant through the loopback forward

Given a macOS developer host that runs no Dolt server

And a per-user LaunchAgent forwarding local `127.0.0.1:3307` to the server host's `127.0.0.1:3307` over SSH

And the checkout's committed `.beads/config.yaml` unchanged

When `/usr/local/bin/with-livespec-env.sh -- bd show <id>` runs from that checkout for an item of this repository's tenant

Then the item MUST be read from the tenant on the server host

And no local beads store, including an `embeddeddolt/` directory, MUST be created on the host
```

## Proposal: just bootstrap names unmet host prerequisites and ledger pointers instead of reporting success

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add a **Bootstrap scope** clause to the new §"Developer host platforms". `just bootstrap` provisions only repository-local obligations. It installs no host tool and does not set `livespec.primaryPath`. It MUST name each unmet host prerequisite and each unmet ledger pointer file, and it MUST then exit non-zero rather than report success. Two scenarios cover a missing ledger pointer and an unsatisfying bare `python3`.

### Motivation

Measured on the MacBook Air during Stage 0 of plan `homelab-k8s-worker-nodes` (livespec-dev-tooling-ko26ez). `just bootstrap` (`uv run python -m livespec_dev_tooling.fleet.local_reconcile`) exited 0 on a fresh clone with no `.beads/metadata.json`. That left the ledger unusable while bootstrap reported success. Bootstrap also does not install host tools. That is correct, because the host toolchain sources are the host's own concern under **Host toolchain sources**. But it means a host missing `python3`, bash 4 or `node` passes bootstrap, and then fails later inside a hook. Bootstrap does not set `livespec.primaryPath`, because the hooks detect the primary checkout structurally (see the justfile comment on `install-commit-refuse-hooks`). The ruling stays narrow: bootstrap names what is missing and does not claim success. It does not acquire a duty to install or regenerate anything.

### Proposed Changes

Add this paragraph to §"Developer host platforms", directly after **Host toolchain sources**:

```markdown
**Bootstrap scope.** `just bootstrap` MUST provision only repository-local obligations. It MUST NOT install a host tool, and it MUST NOT set `livespec.primaryPath`, because the commit-refuse hooks detect the primary checkout structurally. A run MUST check each prerequisite named in **Host toolchain sources**, and each ledger pointer file that AGENTS.md §"Beads runtime prerequisites" requires: `.beads/config.yaml` and `.beads/metadata.json`. For each unmet prerequisite or pointer it MUST print a line that names it and what would satisfy it. Such a line MUST NOT be only a warning. When any is unmet, the run MUST exit non-zero and MUST NOT report success, even when every repository-local obligation reconciled.
```

Append to `scenarios.md`:

```markdown
## Scenario: bootstrap names a missing ledger pointer instead of reporting success

Given a checkout of this repository whose `.beads/config.yaml` is present and whose `.beads/metadata.json` is absent

And a developer host that supplies every host toolchain prerequisite

When `just bootstrap` runs in that checkout

Then its output MUST name `.beads/metadata.json` as an unmet ledger pointer

And it MUST exit non-zero

And it MUST NOT report success

## Scenario: bootstrap names a bare python3 that does not satisfy requires-python

Given a developer host whose first `python3` on `PATH` is older than the version `pyproject.toml`'s `requires-python` requires

When `just bootstrap` runs in a checkout of this repository

Then its output MUST name `python3` and the version `requires-python` requires

And it MUST exit non-zero

And it MUST NOT install or replace any interpreter on the host
```

## Proposal: Delegated gates are required on a non-Linux host, and a gate always ends with a verdict

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add two clauses to §"Developer host platforms". **Gates on a non-Linux host**: on a macOS developer host, the delegated gates are the required route, the host is enrolled as a gates client, and an opted-in push from such a host that cannot read the gates kubeconfig is refused, naming the missing enrollment, instead of running a local fall-through that cannot pass there. **A gate always ends with a verdict**: a gate's pytest session that stops making progress is ended and never read as a pass, and an interrupted delegated wait either resumes on the same gate Job or ends with no verdict, never with a pass. The proposal also amends `contracts.md` §"Delegated pre-push gate" **Host eligibility** with the matching exception, and narrows the existing scenario's Given to a Linux host. It adds three scenarios.

### Motivation

Measured on the MacBook Air during Stage 0 of plan `homelab-k8s-worker-nodes` (livespec-dev-tooling-ko26ez). Several Linux-only members of this repository's suites cannot produce a verdict on macOS. The suite-green replay leg calls `os.sched_getaffinity` at `livespec_dev_tooling/checks/_red_green_replay_suite.py:193`, which macOS's Python does not provide, and other members read `/proc`. So the local `just check` fall-through, which `contracts.md` §"Delegated pre-push gate" **Host eligibility** runs whenever the pushing user cannot read the gates kubeconfig, cannot pass on that host. Falling back to it turns a missing enrollment into a red or hung gate that names the wrong cause. The Mac was enrolled through `/etc/ci-runner/gates.kubeconfig`, and its pushes delegate to the cluster. A Linux host without the credential, such as a factory sandbox, still gates locally, so the exception is keyed on the platform. Two verdict-integrity failures were also observed. In one, pytest-rerunfailures under pytest-xdist deadlocked after its re-runs: 0% CPU for more than 27 minutes, and no verdict. In the other, a delegated gate whose wait was interrupted by host sleep ended NO_VERDICT. The existing contract already refuses a push without a verdict, so no pass was reported, but the gate Job's verdict was abandoned. `contracts.md` §"Suite-green replay leg" **Progress bound** already states a no-progress bound for one leg, as spec-first. This proposal extends the same principle to every gate pytest session and adopts that bound's mechanics and default by reference. Two choices are genuinely open, so both are SHOULD: whether a sleep-interrupted wait resumes on the same Job or ends with no verdict, and whether a stall is reported as a failure or as no verdict. The MUST is only what the facts decide: never a hang and never a pass. Commit-time absent-verdict behaviour (§"Delegated commit-time replay test runs", §"Delegated pre-commit aggregate") is not changed here.

### Proposed Changes

Add these two paragraphs to §"Developer host platforms" in `non-functional-requirements.md`, after **Bootstrap scope**:

```markdown
**Gates on a non-Linux host.** On a developer host whose platform is not Linux (today, macOS), the Linux-only members of this repository's suites cannot produce a verdict locally. There the delegated gates (`contracts.md` §"Delegated pre-push gate") are the required route. Such a host MUST be enrolled as a gates client, so that its login user can read the gates kubeconfig at `/etc/ci-runner/gates.kubeconfig`. In a repository with `delegated_gate = true`, a push from such a host whose user cannot read the gates kubeconfig MUST be refused. The refusal MUST name the missing gates-client enrollment. The push MUST NOT run the local `just check` fall-through, and MUST NOT silently fall back to any local full aggregate. A Linux host keeps the fall-through that §"Delegated pre-push gate" **Host eligibility** describes.

**A gate always ends with a verdict.** A gate run started on a developer host MUST end with a verdict or with an explicit no-verdict state. It MUST NOT hang. This holds for every pytest session that the gate runs, whether on the host or inside a gate Job. A session that has stopped making progress MUST be ended, with its whole process group, pytest-xdist workers included. An example is pytest-rerunfailures re-runs under pytest-xdist deadlocking with every worker idle. The bound SHOULD take its stall window, its default and its override from the mechanics of `contracts.md` §"Suite-green replay leg" **Progress bound**. An ended session MUST NOT be reported as a pass. It SHOULD be reported as a failure naming the stall window. When the gate client's wait on a submitted gate Job is interrupted, for example by host sleep or a network loss, the client MUST do one of two things. It MAY resume waiting on the same gate Job and honour that Job's verdict for the same tree. Otherwise it MUST end with no verdict under §"Delegated pre-push gate" **Verdict**, so the push is refused and the outcome event is `no-verdict`. It MUST NOT report a pass it did not receive from that Job. When the Job still exists after the interruption, the client SHOULD resume waiting on it rather than end with no verdict.
```

In `contracts.md` §"Delegated pre-push gate", append this sentence to the **Host eligibility** bullet, after "A host that holds no gates credential, such as a factory sandbox, therefore keeps gating locally in an opted-in repository.":

```markdown
The exception is a pushing host whose platform is not Linux. There the local fall-through cannot produce a verdict, so the push MUST be refused, naming the missing gates-client enrollment, and MUST NOT gate locally (`non-functional-requirements.md` §"Developer host platforms", **Gates on a non-Linux host**).
```

In `scenarios.md`, in the existing `## Scenario: an opted-in push from a host that cannot read the gates kubeconfig gates locally`, replace the line `And a pushing host where the pushing user cannot read the gates kubeconfig` with `And a Linux pushing host where the pushing user cannot read the gates kubeconfig`. The heading is unchanged.

Append to `scenarios.md`:

```markdown
## Scenario: an opted-in push from an unenrolled macOS host is refused instead of gating locally

Given a consumer repository whose `[tool.livespec_dev_tooling]` table sets `delegated_gate = true`

And a macOS pushing host where the pushing user cannot read the gates kubeconfig

When a git push of a tree that has no green token runs the pre-push gate

Then the push MUST be refused

And the refusal MUST name the missing gates-client enrollment

And the local `just check` fall-through MUST NOT run

And a gate Job MUST NOT be submitted to the `gates` namespace

## Scenario: a gate pytest session that stops making progress ends without a pass

Given a gate run whose pytest session, running pytest-xdist workers, has printed no new output for longer than its stall window

When the stall window elapses

Then the session's whole process group, pytest-xdist workers included, MUST be ended

And the gate MUST end with a verdict or an explicit no-verdict state

And the gate MUST NOT report a pass

## Scenario: a delegated pre-push wait interrupted by host sleep never reports a pass

Given a consumer repository whose `[tool.livespec_dev_tooling]` table sets `delegated_gate = true`

And a pushing host where the pushing user can read the gates kubeconfig

And a push whose gate Job has been submitted for its tree

When the host sleeps while the gate client waits on that gate Job, and then wakes

Then the push MUST complete only on a green verdict that same gate Job reports for that tree

And when the client obtains no verdict from that gate Job, the push MUST be refused and the outcome event MUST be `no-verdict`
```

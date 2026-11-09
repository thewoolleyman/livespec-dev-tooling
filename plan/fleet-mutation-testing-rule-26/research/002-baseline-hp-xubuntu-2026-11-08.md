# Rule-26 test-suite baseline, hp-xubuntu, 2026-11-08

This is the BEFORE measurement that plan assertion 6 requires. It records, for every fleet repository, the exact test
count and the test-only runtime, all taken by one stated method on one host. The AFTER measurement (assertion 7) must
repeat this method exactly, including the overseer deselection below, on the same host.

## Method

- **Host:** hp-xubuntu (Linux 7.0.0-31-generic x86_64, glibc 2.43, 16 cores). It is the plan's measurement host by
  maintainer ruling, because mutmut segfaults on macOS hosts.
- **Tool:** `just fleet-test-baseline <12 clone paths>` from livespec-dev-tooling at `ae1ba3e1`, which carries all three
  recipe fixes this plan landed:
  - livespec-dev-tooling#3778 records a red suite instead of aborting the run.
  - livespec-dev-tooling#3808 counts a doubly quiet pytest collection.
  - livespec-dev-tooling#3820 reads nextest's own `test-count`.
- **Count per ecosystem:**
  - Python: the collected total of `mise exec -- uv run pytest --collect-only -q -p no:cacheprovider`. When a repo's
    `addopts` already holds `-q`, the total is the sum of the per-file counts.
  - Rust: the `test-count` field of `cargo nextest list --message-format json`.
  - Shell: one per executed `*.test.sh`.
- **Runtime:** `time.perf_counter` around each repository's test-only command, never the `just check` aggregate. The
  commands are:
  - Python: `mise exec -- uv run pytest -q`.
  - Rust: `cargo nextest run --workspace --all-features`.
  - Shell: `bash <script>` for each script.
- **Run:** started 2026-11-08T19:35:52Z and finished 23:19:47Z, detached on the host. Every clone was at its current
  `origin/master`; the revisions are listed below. The two private repositories were refreshed from git bundles of
  chads-macbook-pro's `origin/master`.

### livespec-overseer is measured with `tests/prompts/` deselected

In the full run, overseer's suite HUNG. After 82 minutes it had used 4 minutes of CPU and made no further progress: the
main thread was in `poll`, and a second thread was in `accept` on a loopback port. The cause is that **tmux is not
installed on hp-xubuntu**. Overseer's `tests/prompts/` rig tests drive a real tmux, and they deliberately fail rather than
skip without one. On this host they error, and the run then stalls after the errors. A verbose diagnostic reproduced the
stall at `tests/prompts/test_emitted_commands_discriminate.py::test_the_bare_pane_resolution_returns_the_supervisors_own_pane`.
The plan session sent TERM to that one pytest process, and the recipe recorded it as a red suite (exit 143), so the
remaining three repositories were still measured.

**Decision:** overseer's runtime is measured with `tests/prompts/` excluded. The legacy-coordinator-agent made this
decision under delegated authority R301 at 2026-11-09T00:16Z. It is NOT a maintainer ruling, and the maintainer's word
overrides it if they differ. (The measurement JSON's method string says "maintainer ruling"; that is wrong.) Its
conditions are that the exclusion is stated here and repeated identically for the after measurement.

The exclusion is the recipe's own commands plus `--ignore=tests/prompts`, for the count and for the timed run:

- count: `mise exec -- uv run pytest --collect-only -q -p no:cacheprovider --ignore=tests/prompts`
- run: `mise exec -- uv run pytest -q --ignore=tests/prompts -o faulthandler_timeout=300` (the faulthandler option only
  dumps stacks if a test passes 300 s; it does not change what runs)

The run started at 2026-11-09T00:16:56Z and finished at 00:55:58Z, with overseer at the same revision `fa7703cb`.

## Results

| repository | ecosystem | tests | test-only runtime (s) | test exit |
|---|---|---:|---:|---:|
| livespec | python | 1,759 | 170.3 | 0 |
| livespec-orchestrator-beads-fabro | python | 14,077 | 5,300.7 | 0 |
| livespec-dev-tooling | python | 8,471 | 1,668.5 | 1 |
| livespec-runtime | python | 453 | 8.3 | 0 |
| livespec-driver-claude | python | 2,169 | 20.9 | 0 |
| livespec-driver-codex | python | 862 | 17.2 | 0 |
| livespec-driver-pi | python | 67 | 1.2 | 0 |
| livespec-orchestrator-git-jsonl | python | 485 | 11.0 | 0 |
| livespec-overseer (`tests/prompts/` deselected) | python | 4,550 | 2,113.7 | 1 |
| livespec-console-beads-fabro | rust | 2,105 | 35.5 | 0 |
| livespec-tdd-proof | python | 5 | 0.4 | 0 |
| dolt-server | shell | 21 | 30.6 | 1 |
| **fleet total** | | **35,024** | **9,378.4** | |

- The fleet totals are the sums of the rows above. The runtime total is summed from the unrounded measurements, so it
  differs by 0.1 s from the sum of the rounded cells.
- Overseer's full collected count is 4,715, so the fleet total with overseer undeselected is 35,189. The before/after
  comparison uses the deselected 4,550, because that is the set whose runtime could be measured on this host.
- The full run's overseer row (4,715 tests, 5,050.0 s, exit 143) is NOT a runtime figure, because 5,050 s is the hang
  plus the TERM.

## Red suites

A red suite is timed as it ran. Its exit status is recorded, and the run continues. The recipe does not keep test output,
so the failing tests below are attributed only where this session observed them.

- **livespec-dev-tooling (exit 1):** the failing tests were not captured in this run. The earlier handoff observed
  `test_pool_node_rebuild_scenario` red on hp-xubuntu, because it reads the host's real `/etc/rancher/k3s/agent-join-token`.
  That observation was not re-verified here.
- **dolt-server (exit 1):** not captured in this run. The earlier handoff observed three `*.test.sh` checks failing on a
  host-dependent missed-cycle count.
- **livespec-overseer (exit 1, deselected run):** nine more tests need a real tmux and fail, without hanging, after flake
  retry's four attempts each:
  - six in `tests/integration/test_ready_arm_until_idle_live_tmux.py`
  - `tests/test_codex_unindexed_adoption.py::test_mapped_unindexed_codex_adoption_uses_a_real_tmux_session`
  - `tests/test_overseer_declare.py::test_fake_session_cli_prints_contract_and_restarts_in_real_supervisor_loop`
  - `tests/test_tmux_automation_shell.py::test_live_tmux_pane_inherits_the_automation_shell_marker`

  They are included in the deselected count and runtime, and the after measurement must keep them in the same way.

## Load caveat

hp-xubuntu is a factory node, and factory pods ran throughout. The 1-minute load average was sampled every minute
alongside both runs:

- **Full run** (224 samples, 19:35Z to 23:18Z): minimum 0.0, 25th percentile 4.8, median 10.5, 75th percentile 18.8,
  maximum 67.0, mean 14.5. Load was above the 16-core count in 29% of the minutes.
- **Overseer deselected run** (40 samples): median 13.0, maximum 33.1.

Runtimes therefore carry contention noise; the orchestrator's 88 minutes, in particular, ran under the heaviest load. The
after measurement should record load the same way. A runtime improvement smaller than this noise must not be claimed
from one pair of runs.

## Findings

1. **hp-xubuntu has no tmux.** This made overseer's `tests/prompts/` rig tests error and then stall the run. Fixing it
   belongs to whoever owns hp-xubuntu's tool set. A user-level `mise use -g tmux@3.5a` was refused in this session as a
   shared-host change. Separately, overseer's owner may want to look at why the run stalls after those errors instead of
   failing.
2. **Growth since the 2026-10-28 survey** (research note 001, same collect method on another host):
   - orchestrator: 11,672 → 14,077 tests
   - dev-tooling: 5,520 → 8,471 tests
   - overseer: 3,780 → 4,715 tests
   - console: 2,079 by the old `::` approximation → 2,105 by `test-count`
3. **Three recipe defects** surfaced only on a real 12-repository run, and each is fixed: aborting on one red suite,
   failing to parse a doubly quiet collection, and a Rust count that always read 0. Each test had faked a shape the real
   tool does not produce, or no fixture covered the case.

## Revisions measured

```
livespec 5727bef696cf656318d91f8987235e8f7fa2ff68
livespec-orchestrator-beads-fabro 53d6398eb1d42eeeb511f048575609de173b0a8c
livespec-dev-tooling ae1ba3e132bff89929827717b89ba89bba94c36c
livespec-runtime fcee5121b34292473b6696829fa55357bb6f00aa
livespec-driver-claude b5baccfc7b465aa025fcf05dc04c13c81853b194
livespec-driver-codex ec0e09877489effb829e3d76c3aa4dd74f84560f
livespec-driver-pi f1a576fb298bf2c18fb3000c0b1bc5dba63888d2
livespec-orchestrator-git-jsonl 34eea0931aecdbc6256acbfc37f894ecc1e47f70
livespec-overseer fa7703cb549e1e134d8deacdb0d50e806461b3ed
livespec-console-beads-fabro a00b1eb66f54def0593af72202afc889b6cacb43
livespec-tdd-proof df3a3ceec80d280b1bb11d7021eeb6cc744b9b27
dolt-server 8e0501c03cf46c74349a29ab5a2f404665b70f61
```

Raw artefacts are on hp-xubuntu:
- `~/rule26-baseline/baseline-20261108T1935Z.{json,revisions,load,done}`
- `~/rule26-baseline/overseer-excl-prompts-20261109T0016Z.{json,meta,load,done}`

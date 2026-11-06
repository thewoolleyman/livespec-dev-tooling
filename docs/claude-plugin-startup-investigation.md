# Claude plugin startup latency

## Problem

The blocking SessionStart hook runs `just ensure-plugins`, which issued twelve
Claude plugin commands serially on every start, including marketplace
registration and plugin install/update for plugins that were already current.
On the maintainer's macOS host that took 25.6–151 seconds. Per-command spikes
moved between commands; their underlying cause is not established.

## Measurements (2026-11-05)

- VPS `vmi3006760`, unchanged recipe through ordinary SSH:
  `/usr/bin/time -p mise exec -- just ensure-plugins` exited 0 in real 26.47s
  (user 15.99s, sys 14.25s) with every plugin already current. One sample,
  not a distribution. A single `claude plugin marketplace list` took 1.17s.
- macOS developer host: four concurrent `git ls-remote` probes for the declared
  release refs finished in 0.521s total and matched the installed registry
  `gitCommitSha` values. This measures ref discovery only.

Each `claude` subcommand also reads the user's OAuth credential from the macOS
login Keychain. While that Keychain was locked on the measured host, every such
short-lived process produced its own unlock request, so redundant plugin
commands also multiply Keychain traffic. Skipping proven-current commands
reduces both latency and that traffic; it is not a fix for a locked Keychain.

## Change

- Compare each declared marketplace source/ref with `known_marketplaces.json`
  and resolve moving GitHub refs with at most four parallel `git ls-remote`
  probes, each bounded to five seconds. A full immutable commit pin needs no
  network lookup. Comparing only local cached refs would miss new releases.
- Skip registration only for a matching installed marketplace, and plugin
  install/update only for a matching project-scope registry commit.
- Unestablished currency (probe failure, timeout, unsupported source) falls
  back to the ordinary reconcile path.
- Always verify registry and artifact content. After repairing an established
  cache defect, run the complete provisioning cycle even if the first cycle
  skipped commands.
- Preserve reporting of every CLI refusal and the distinct invocation-failure
  handling in `_run_commands` (`livespec-dev-tooling-357j2y`).
- Append one record per CLI command to mode-0600
  `~/.local/state/livespec-dev-tooling/plugin-commands.jsonl`: start/end
  timestamps, PID, argv, elapsed time, and whether it was invoked and how it
  ended. Child streams and environment are never logged.

No hook timeout is added: killing a reconcile midway must not be reported as
successful provisioning, so a timeout needs explicit failure semantics first.

## Verification

`tests/livespec_dev_tooling/fleet/test_plugin_startup_currency.py` specifies
that a current host issues zero provisioning commands, plus verification and
cache-repair behavior. `test_plugin_startup_probes.py` covers ref resolution,
probe failure and timeout, unsupported sources, immutable pins and command
logging. Warm-start timing on a real host is measured after release.

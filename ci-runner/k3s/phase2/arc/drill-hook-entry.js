#!/usr/bin/env node
'use strict'
// drill-hook-entry.js -- TEMPORARY. livespec-dev-tooling-4oeffe bullet-3
// straddle drill. It exists only between the drill's PR-A and its revert
// (PR-B).
//
// A pass-through runner container hook entry point carried IN the
// hook-template ConfigMap, the way the git-seed hook was on 2026-11-04. It
// loads the fleet-patched ARC hook from its node path. That bundle runs its
// `run()` unconditionally on load and reads the runner's JSON line from the
// inherited stdin, so every hook command reaches it byte for byte.
//
// The drill: runner pods started under the revision carrying this file have
// ACTIONS_RUNNER_CONTAINER_HOOKS naming /home/runner/hook-template/<this file>.
// The revert's converge removes the key. Under the per-revision ConfigMaps
// (39b29b472), such a pod keeps mounting its own immutable revision, so its
// teardown still finds this entry point. Before that change, it failed with
// "Executing the custom container implementation failed".
require('/home/runner/fleet-hook/index.js')

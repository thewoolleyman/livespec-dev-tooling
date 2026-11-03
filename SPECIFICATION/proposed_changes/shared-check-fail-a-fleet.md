---
topic: shared-check-fail-a-fleet
author: claude-opus-5-5
created_at: 2026-11-03T01:20:54Z
---

## Proposal: A shared per-commit check that fails a plugin release whose Codex hook the hook-cache reconciler cannot cover

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a canonical shared per-commit check, `codex_hook_reconcilable`, as a `### ` subsection under §"Shared check inventory" in contracts.md, and add one scenario per load-bearing behaviour to scenarios.md. The check locates every Codex plugin hooks file a repository ships (the file named by a `.codex-plugin/plugin.json` `hooks` entry, and the default `hooks/hooks.json` beside it), and fails, naming the plugin manifest, the hook event and the command, when a hook command mentions `CLAUDE_PLUGIN_ROOT` but carries no `${CLAUDE_PLUGIN_ROOT}/` path. It fails, naming the missing path, when a command's first `${CLAUDE_PLUGIN_ROOT}/` entrypoint is not in the plugin payload, and fails, naming the file, when a hooks file cannot be parsed as JSON. It passes on hooks wrapped in shell conditionals and invoked through `python3` or `bash` with existing entrypoints, and passes on a repository that ships no Codex plugin while reporting that it examined zero manifests. Because the module lives under `checks/`, every consumer's `just check` must wire it, which is the intended effect: a fleet plugin cannot release a Codex hook the reconciler cannot cover.

### Motivation

The livespec-driver-codex hook-cache reconciler (Driver specification v014, change `codex-hook-cache-all-plugins`, §"Codex hook-cache compatibility") keeps superseded hook paths alive for every covered plugin, but only when each hook entrypoint is a `${CLAUDE_PLUGIN_ROOT}/` path present in the plugin payload. For any other shape it fails its reconcile and claims no hook continuity, which an operator first sees after the plugin has already been released and installed. Work item livespec-dev-tooling-yhacv6 asks for the release-gating half of that fix: a shared check every fleet plugin repository's `just check` runs, so the uncoverable shapes are rejected at the producing plugin's own gate before release. The factory held that item on 2026-11-03 at 01:13Z with a spec-stated judgement that the ratified text names no check that parses a Codex plugin hooks.json and states none of the four behaviours the item asks for (the `CLAUDE_PLUGIN_ROOT` path rule, the missing-entrypoint failure, the unparseable-JSON failure, and the passing shapes), and that §"Shared check inventory" is the section a new entry would extend. This proposal supplies that text. Origin: livespec bug livespec-gqjkge and plan epic livespec-3rfjga, both in the livespec repository. The in-flight survey found four remote `spec/*` branches and one open spec pull request (#3177, the v116 untouched-test-retry revise, which appends to scenarios.md); none touches §"Shared check inventory" or Codex hooks, so this proposal aligns with all of them under the configured default-align policy.

### Proposed Changes

In SPECIFICATION/contracts.md §"Shared check inventory", insert a new `### `-level subsection immediately after the `### \`no_shadow_ledger_body_identical\` check` subsection, that is, after its final paragraph, which reads verbatim:

> Consumers wire the check into `just check` aggregates and CI matrices per the same migration-phase discretion as concern #1: each Driver's wiring lands with that Driver's own hook-refactor slice.

and before `## Consumer configuration schema`. The inserted subsection reads:

### `codex_hook_reconcilable` check

Invocation: `python -m livespec_dev_tooling.checks.codex_hook_reconcilable`, wired as the `check-codex-hook-reconcilable` recipe. Exit `0` on pass OR skipped, exit `4` with structured stderr findings on fail.

This is a canonical per-commit check: it lives under `livespec_dev_tooling/checks/`, so it is a member of the canonical check set, and every consumer MUST wire it into its `just check` aggregate and its CI matrix per this section and the wiring-completeness invariant. That conscription is the purpose of the placement, not a side effect of it. The check exists so that a fleet plugin whose Codex hook the `livespec-driver-codex` hook-cache reconciler cannot cover fails the producing repository's own gate before it is released. An opt-in workflow-check placement would let exactly the repository that forgets to adopt the check release such a hook, so the workflow-check placement is rejected. The consequence of the placement is stated here rather than left implicit: once a consumer's library pin reaches the release that ships this module, that consumer's `check-aggregate-completeness` and the fleet-conformance row `canonical-check-slugs-wired` MUST report the slug as unwired until the consumer either wires `check-codex-hook-reconcilable` or declares a reasoned waiver under §"Shared check inventory" **Canonical-check waivers**. A repository that ships no Codex plugin owes the wiring and nothing else: the check passes there, as stated below.

The reason the check exists is the reconciler's contract, which the Driver owns at `livespec-driver-codex/SPECIFICATION/contracts.md` §"Codex hook-cache compatibility" (Driver specification v014, change `codex-hook-cache-all-plugins`). The reconciler keeps a superseded hook path alive for every covered plugin, but only when each hook entrypoint is a `${CLAUDE_PLUGIN_ROOT}/` path that exists in the plugin's payload; for any other shape it MUST fail its reconcile for that plugin and MUST NOT claim hook continuity. This check applies the same entrypoint rules at the producing plugin's own gate. It is the release-gating half of the fix for livespec bug `livespec-gqjkge` (plan epic `livespec-3rfjga`, both in the `livespec` repository). The check is not the whole of the reconciler's validation: the reconciler additionally compiles each `.py` entrypoint under the bare interpreter Codex executes, which this check does not do.

Inputs are project-agnostic: no `[tool.livespec_dev_tooling]` role keys are consumed, so the check qualifies under the configurability partition criterion above without any role-key wiring. Its sole inputs are the files git tracks in the repository, because the tracked tree is what a plugin release ships. The check performs no network I/O.

**Locating the hooks files.** A **Codex plugin manifest** is any tracked file named `plugin.json` whose parent directory is named `.codex-plugin`. The manifest's **plugin root** is the parent of that `.codex-plugin` directory, and the **plugin payload** is the set of tracked files under the plugin root. For each manifest, the check MUST examine the union of every hook declaration the plugin ships, which is the same discovery rule the reconciler applies:

- When the manifest carries a `hooks` entry whose value is a string, or a list of strings, each string names a Codex plugin hooks file by a path relative to the plugin root. When the value is an object, it is itself a hook declaration in the hooks-file shape and is examined in place.
- The default hooks file `hooks/hooks.json` under the plugin root, when it exists in the payload, is also examined, whether or not the manifest carries a `hooks` entry.

A manifest with no `hooks` entry and no default hooks file ships no Codex plugin hooks and contributes no command to examine; it is not a failure.

**Examining each command.** In a hooks file, the `hooks` object maps each hook event name (for example `PreToolUse`, `SessionStart` or `Stop`) to a list of matcher groups, and each group carries a `hooks` list of entries. The check MUST examine every entry that carries a `command` string, for every hook event, and for each such command:

1. If the command does not mention `CLAUDE_PLUGIN_ROOT` in any form, it has no versioned path for the reconciler to preserve, and the check MUST NOT examine it further. It passes.
2. If the command mentions `CLAUDE_PLUGIN_ROOT` but carries no `${CLAUDE_PLUGIN_ROOT}/` path, the check MUST fail (`failure_mode` `no_plugin_root_path`), naming the plugin manifest, the hook event and the command. A command that spells the variable without braces, such as `$CLAUDE_PLUGIN_ROOT/hooks/guard.py`, or that uses it bare, falls under this rule, because the reconciler recognises only the braced `${CLAUDE_PLUGIN_ROOT}/` form.
3. Otherwise the command's **entrypoint** is the first `${CLAUDE_PLUGIN_ROOT}/` path in it, whether the command invokes that path through `python3` or `bash` or places it inside a shell conditional. The path is resolved against the plugin root. If it does not name a file in the plugin payload, the check MUST fail (`failure_mode` `entrypoint_missing`), naming the missing path, the plugin manifest, the hook event and the command. A path that resolves outside the plugin root names no file in the payload and fails under this rule.

**Unreadable declarations.** The reconciler fails loudly on an unreadable or malformed hook declaration, so the check MUST fail on the same inputs rather than skip them:

- A hooks file that cannot be parsed as JSON MUST fail (`failure_mode` `unparseable_hooks_file`), naming the file.
- A hooks file that parses but is not an object carrying a `hooks` object of event names mapping to lists of matcher groups MUST fail (`failure_mode` `malformed_hooks_file`), naming the file.
- A manifest that cannot be parsed as JSON MUST fail (`failure_mode` `unparseable_manifest`), naming the manifest, because the check cannot then tell which hooks files the plugin ships.
- A manifest whose `hooks` value is not a string, a list of strings or an object MUST fail (`failure_mode` `malformed_manifest`), naming the manifest.
- A hooks file that a manifest's `hooks` entry names but that is not in the plugin payload MUST fail (`failure_mode` `hooks_file_missing`), naming the manifest and the missing path. The absence of the default `hooks/hooks.json` is not a failure.

**Passing shapes.** A plugin whose hook commands are each wrapped in a shell conditional, such as `if [ -n "${CODEX_THREAD_ID:-}" ]; then exit 0; fi; python3 "${CLAUDE_PLUGIN_ROOT}/hooks/session_wait_stop.py"`, or written bare, such as `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/no_shadow_ledger.py"` or `bash "${CLAUDE_PLUGIN_ROOT}/hooks/guard.sh"`, and whose every entrypoint names a file in the payload, MUST pass.

**Exit and reporting.** The check MUST examine every manifest and every hooks file before it exits, and MUST report every failure it finds rather than stopping at the first. It MUST exit `4` when it emits one or more `fail` findings, and `0` otherwise. A pass is never silent: on every exit `0` the check MUST emit one structured `info` event carrying `check_id`, `manifests_checked` (the number of Codex plugin manifests it found) and `commands_checked` (the number of hook commands it examined), so a repository that ships no Codex plugin reports `manifests_checked: 0` with a message saying that the repository ships no Codex plugin hooks, and a reader can tell a pass that examined nothing from a pass that examined every hook. When the working directory is not inside a git working tree, or `git` is not on PATH, the check MUST exit `0` with an `info` or `warning` event carrying `check_id` and the reason it skipped, consistent with the sibling checks' graceful-skip convention.

Each `fail` finding carries:

- `check_id`: `codex_hook_reconcilable`
- `status`: `fail`
- `failure_mode`: one of `no_plugin_root_path`, `entrypoint_missing`, `unparseable_hooks_file`, `malformed_hooks_file`, `unparseable_manifest`, `malformed_manifest` or `hooks_file_missing`
- `manifest`: the repository-relative path of the Codex plugin manifest the finding concerns
- `path`: the repository-relative path of the file the finding concerns — the hooks file for a command or hooks-file finding (the manifest itself when the declaration is inline in it), and the manifest for a manifest finding
- `event`: the hook event name for `no_plugin_root_path` and `entrypoint_missing`; empty (`""`) otherwise
- `command`: the full hook command for `no_plugin_root_path` and `entrypoint_missing`; empty (`""`) otherwise
- `entrypoint`: for `entrypoint_missing`, the repository-relative path the entrypoint resolved to; for `hooks_file_missing`, the repository-relative path of the missing hooks file; empty (`""`) otherwise
- `message`: a sentence naming the manifest and, where they apply, the hook event, the command and the missing path
- `hint`: for `no_plugin_root_path`, to root the hook's entrypoint at `${CLAUDE_PLUGIN_ROOT}/` so the reconciler can preserve it; for `entrypoint_missing` and `hooks_file_missing`, to ship the named file in the plugin payload or correct the path; for the parse and shape modes, to repair the named file
- `line`: 0

In SPECIFICATION/scenarios.md, append the following five scenarios. Each one exercises the rule stated in contracts.md §"`codex_hook_reconcilable` check", which carries the full rule.

## Scenario: a Codex plugin hook command that mentions CLAUDE_PLUGIN_ROOT without a braced plugin-root path fails the producing repository's gate

Given a repository that tracks `.claude-plugin/.codex-plugin/plugin.json` and a default `.claude-plugin/hooks/hooks.json` whose `SessionStart` event declares the command `python3 "$CLAUDE_PLUGIN_ROOT/hooks/start.py"`

When `python -m livespec_dev_tooling.checks.codex_hook_reconcilable` runs in that repository

Then it MUST exit `4`

And it MUST emit a `fail` finding with `failure_mode` `no_plugin_root_path` whose `manifest` is `.claude-plugin/.codex-plugin/plugin.json`, whose `event` is `SessionStart`, and whose `command` is that command

## Scenario: a Codex plugin hook entrypoint missing from the plugin payload fails the producing repository's gate

Given a repository that tracks `livespec/.codex-plugin/plugin.json` with a `hooks` entry of `./hooks/hooks.json`, whose `Stop` event declares the command `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/gone.py"`, and that tracks no file `livespec/hooks/gone.py`

When `python -m livespec_dev_tooling.checks.codex_hook_reconcilable` runs in that repository

Then it MUST exit `4`

And it MUST emit a `fail` finding with `failure_mode` `entrypoint_missing` whose `entrypoint` is `livespec/hooks/gone.py`, and which names the manifest, the `Stop` event and the command

## Scenario: an unparseable Codex plugin hooks file fails the producing repository's gate

Given a repository that tracks a Codex plugin manifest and a default hooks file whose content is not valid JSON

When `python -m livespec_dev_tooling.checks.codex_hook_reconcilable` runs in that repository

Then it MUST exit `4`

And it MUST emit a `fail` finding with `failure_mode` `unparseable_hooks_file` whose `path` names that hooks file

## Scenario: Codex plugin hooks wrapped in shell conditionals with existing plugin-root entrypoints pass

Given a repository that tracks a Codex plugin manifest and a default hooks file declaring one command `if [ -n "${CODEX_THREAD_ID:-}" ]; then exit 0; fi; python3 "${CLAUDE_PLUGIN_ROOT}/hooks/a.py"` and one command `if [ -n "${CODEX_THREAD_ID:-}" ]; then exit 0; fi; bash "${CLAUDE_PLUGIN_ROOT}/hooks/b.sh"`, and that tracks both `hooks/a.py` and `hooks/b.sh` under the plugin root

When `python -m livespec_dev_tooling.checks.codex_hook_reconcilable` runs in that repository

Then it MUST exit `0`

And it MUST emit an `info` event with `manifests_checked` `1` and `commands_checked` `2`

## Scenario: a repository that ships no Codex plugin passes the Codex hook check and reports that it examined nothing

Given a git repository that tracks no file named `plugin.json` under a `.codex-plugin` directory

When `python -m livespec_dev_tooling.checks.codex_hook_reconcilable` runs in that repository

Then it MUST exit `0`

And it MUST emit an `info` event with `manifests_checked` `0` and `commands_checked` `0` and a message saying that the repository ships no Codex plugin hooks

Heading co-edit: this proposal adds no `## ` heading to contracts.md (the new subsection is a `### ` heading beneath `## Shared check inventory`). It adds the five `## Scenario:` headings above to scenarios.md. The revise that accepts it MUST therefore, in the same change, add one `tests/heading-coverage.json` row per new scenario heading, each a spec-first `"test": "TODO"` row with `spec_root` `SPECIFICATION`, `spec_file` `scenarios.md`, `work_item` `livespec-dev-tooling-yhacv6`, and a `reason` that names the integration tier, for example: "Spec-first: a real test at the integration tier or above is owed for this heading, running `python -m livespec_dev_tooling.checks.codex_hook_reconcilable` as a subprocess against a fixture git repository in the scenario's shape and asserting its exit code and structured stderr. livespec-dev-tooling-yhacv6 owns it." The same change MUST regenerate `tests/heading-coverage-debt.json` with `just generate-heading-coverage-debt-register`.


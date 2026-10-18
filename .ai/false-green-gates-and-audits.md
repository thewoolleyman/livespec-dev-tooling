# False Greens In Gates And Fleet Audits

Use this when a gate is green but reality is not, when writing a gate or
fixture that replays a production step, when auditing `.livespec.jsonc` keys
across fleet repositories, or when a coverage report dies on a source file that
no longer exists. Each section records a measured case in which the instrument
returned a plausible answer with no error. Carried from session auto-memory on
2026-10-18; measurement dates are given per section.

## A gate can be green because it performs the step it verifies

Measured 2026-09-04 in livespec-orchestrator-beads-fabro. For four days every
factory dispatch fleet-wide died in setup at exit 127 on an unexpanded
template input token, while `check-fresh-clone-setup` stayed green with
"every conformance setup step passes on a fresh clone".

Both statements were true. `orchestrator-image/fresh-clone-setup-gate.sh`
resolves the repository's integration contract, substitutes every input token
itself, unescapes the TOML quoting, and only then replays the steps. The
production path shipped the same steps unsubstituted. The gate proved the
commands work; nothing proved their delivery did.

The sibling static gate failed the same way from the other side:
`check-seam-equivalence` compared the input declarations, the tokens the
payload references, and the rendered inputs — three host-side artifacts that
all agreed. The engine, the fourth party, had never agreed to any of it.

A gate that reimplements a production step to test it has become a second
implementation, and a divergence between the two is invisible to the gate by
construction. A fixture, a test harness, or a replay script that "sets things
up the way production does" is the same shape.

**How to apply:** when a gate is green but reality is not, list who performs
each step in the gate and who performs it in production, and diff the two lists
rather than re-reading the assertions. When writing such a gate, make it
consume the production path's own output rather than reconstructing it, or
state in the gate which half of the behavior it does not cover. The
`fabro create` / `fabro dump` probe in `.ai/fabro-dispatch-diagnosis.md` is one
way to observe the production side directly.

## `.livespec.jsonc` keys live inside the plugin block

Measured 2026-09-04. The orchestrator's `declaration_from_config_text`
(`_dispatcher_integration_declaration.py`) reads
`parsed["livespec-orchestrator-beads-fabro"]` and resolves every documented key
path relative to that block. A schema key written as
`dispatcher.prepare_toolchain.mise` therefore lives at:

```jsonc
{ "livespec-orchestrator-beads-fabro": { "dispatcher": { "prepare_toolchain": { "mise": [...] } } } }
```

`default_branch` is a sibling of `dispatcher` inside that block, not a child of
it.

Checking for a top-level `dispatcher` key returns nothing for every repository
in the fleet. On 2026-09-04 that lookup nearly shipped "0 of 14 repos declare
this" instead of the true "1 of 14" — a plausible, self-consistent, error-free
wrong answer.

**How to apply:** when auditing `.livespec.jsonc` across repositories, descend
into the plugin block first, and check the audit against a repository you know
declares the key (the schema-owning repository usually does) before believing
an empty result.

## A cold uv cache leaves phantom files in subprocess coverage

Measured 2026-09-06 (`livespec-dev-tooling-5xh8`). On a cold uv cache,
`uv run` writes `get_interpreter_info.py` plus a vendored `packaging/` into
`$UV_CACHE_DIR/.tmpXXXX/python/`, runs it with the project's `.venv` python —
whose pytest-cov `.pth` hook is armed when `COVERAGE_PROCESS_START` is set —
and then deletes the directory. The combined `.coverage` data then lists files
with no source on disk. pytest-cov's inline report ignores errors and only
warns "Couldn't parse"; a strict reporter (`Coverage.json_report`, or
`coverage report` without `-i`) raises `coverage.exceptions.NoSource`. Only
cold pods hit it, so master pushes with a warm cache passed while PR pods
failed deterministically, and three attempts were burned re-running a tree
that was at 100%.

Reproduce in one line:
`UV_CACHE_DIR=<fresh> COVERAGE_PROCESS_START=<rc> uv run --no-sync python -c pass`.

`per_file_coverage.py` now drops these vanished sources centrally (its module
docstring records the mechanism). `CoverageData.purge_files` is not enough on
its own: it removes a file's line and arc rows but keeps the file row, which
reporters still walk, so a filtered rewrite of the data file is needed.

**How to apply:** when a coverage report dies on a path under
`.cache/uv/.tmp*`, or any path that no longer exists, do not debug the tree or
re-run. Check whether the reporting step tolerates vanished sources.

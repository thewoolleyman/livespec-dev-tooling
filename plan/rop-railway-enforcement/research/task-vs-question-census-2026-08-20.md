# The census: 11 tasks, 223 questions — and the tasks are FIVE functions in ONE repo

`the-nine-2026-08-19.md` estimated that "roughly 93% of the other ~200 convictions
are QUESTIONS rather than TASKS" and did not enumerate them. This note **measures**
it, fleet-wide, and the enumeration changes the shape of the whole track.

**Measured 2026-08-20**, shipped basis (`_`-file skip ON), each member at its
then-current master, after `livespec-runtime#590` and
`livespec-orchestrator-beads-fabro#1627` landed.

## The criterion

A conviction is a **TASK** if the function ORIGINATES an expected failure — it
contains a `raise`, or a non-discharging `try` (a handler that re-raises, or a
bare `try/finally`, which propagates). Otherwise it is a **QUESTION**: the check
convicts it for its RETURN TYPE, but there is no expected failure to put on a
failure track, so "convert it" is not a well-formed instruction.

This is `the-nine`'s own stated membership criterion, applied mechanically with
`ast` instead of by reading.

## The census

| member | TASKS | QUESTIONS | total |
|---|---:|---:|---:|
| `livespec-overseer` | **10** | 172 | 182 |
| `livespec-orchestrator-beads-fabro` | **1** | 17 | 18 |
| `livespec` | 0 | 14 | 14 |
| `livespec-runtime` | 0 | 13 | 13 |
| `livespec-orchestrator-git-jsonl` | 0 | 4 | 4 |
| `livespec-driver-codex` | 0 | 3 | 3 |
| `livespec-driver-claude` | 0 | 0 | 0 |
| `livespec-console-beads-fabro` | 0 | 0 | 0 |
| `livespec-dev-tooling` | 0 | 0 | 0 |
| **TOTAL** | **11** | **223** | **234** |

**11 + 223 = 234.** Re-added here, not carried. **95.3% are questions** — the
earlier ~93% estimate was close, and is now measured with a list-producing
harness rather than inferred.

## ⛔ THE TASKS, ENUMERATED — because a count without a list is what this track
keeps getting wrong

`livespec-overseer` — **10 convictions are FIVE functions counted twice**, once
under `overseer/` and once under the byte-identical `.claude-plugin/overseer/`
mirror:

| function | in `the-nine`? |
|---|---|
| `foreman_act_filing.py:173 file_work_item` | yes |
| `foreman_act_ledger.py:69 ledger_mutation` | ⛔ **NO — the-nine MISSED it** |
| `foreman_blocked_answer.py:157 act_blocked_session_answer` | yes (letter only) |
| `foreman_gather_sources.py:70 run_json_command` | yes |
| `foreman_gather_sources.py:92 read_journal` | yes |

`livespec-orchestrator-beads-fabro` — its single "task" is
`plan/beads-v1-1-2-upgrade/rehearsal-package/wrappers/identity-probe.py:71 main`,
which `the-nine` ALREADY ruled is not product code: a rehearsal scratch wrapper,
in the universe by path rather than by intent. **So beads-fabro has ZERO real
tasks left.**

## ▶️ WHAT THIS MEANS FOR THE TRACK

**The entire remaining task-shaped ROP remediation in the fleet is FIVE distinct
functions, all in `livespec-overseer`.** Not 338. Not 234.

And all five are **BLOCKED** on one unratified contract conflict: overseer's
`SPECIFICATION/constraints.md` §"Language and dependencies" makes the supervision
package standard-library-only, which `dry-python/returns` cannot satisfy. See the
ledger entry of 2026-08-20 and `overseer-railway-blocked.patch`.

⚠️ **`livespec-runtime` now has ZERO task-shaped offenders** — its remaining 13
are all questions. The same is true of `livespec`, `git-jsonl` and
`driver-codex`. There is no unblocked conversion work anywhere in the fleet.

## ⛔ `the-nine` IS WRONG IN BOTH DIRECTIONS on overseer

It **includes** `codex_sessions.py:139 proc_fd_targets`, which raises nothing and
whose two handlers both discharge (`return []`, `continue`) — its docstring calls
that "fail-soft to []", and that IS its contract. It **omits**
`foreman_act_ledger.py:69 ledger_mutation`, which raises `RuntimeError` on a
non-zero subprocess exit, exactly like the `file_work_item` it did include.

Neither error is fatal to the note's purpose, but "the nine" should be read as
"a hand-picked sample", not as the task set. **The task set is the five above.**

## The harness

Deliberately NOT committed as a `.py`: a file under `plan/` is first-party Python,
enters `resolve_check_universe()`, and would become an offender in its own census.
Run from each member's root with `uv run --no-sync python`.

```python
import ast
from pathlib import Path
from livespec_dev_tooling.checks.public_api_result_typed import _find_offenders
from livespec_dev_tooling.checks._public_api_consumption import (
    repo_local_public_names, declared_public_names)
from livespec_dev_tooling.checks._no_expected_failure_mode import (
    functions_without_expected_failure_mode)
from livespec_dev_tooling.checks._declared_absence_returns import declared_absence_names
from livespec_dev_tooling.checks._single_meaning_variants import declared_variant_names
from livespec_dev_tooling.config import load_config, resolve_check_universe

config = load_config(repo_root=Path.cwd())
root, universe = resolve_check_universe()
sources = {rel: (root / rel).read_text(encoding="utf-8") for rel in universe}
public = repo_local_public_names(sources=sources) | declared_public_names(
    declared=config.cross_repo_public_api, sources=sources)
total = functions_without_expected_failure_mode(sources=sources, io_trees=config.io_trees)
total |= declared_absence_names(declared=config.total_absence_returns, sources=sources)
total |= declared_variant_names(
    declared=config.single_meaning_variants, sources=sources, io_trees=config.io_trees)

def classify(src, name):
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            raises = [n for n in ast.walk(node) if isinstance(n, ast.Raise)]
            nd = 0
            for t in [n for n in ast.walk(node) if isinstance(n, ast.Try)]:
                for h in t.handlers:
                    if any(isinstance(x, ast.Raise) for x in ast.walk(h)):
                        nd += 1
                if not t.handlers and (t.finalbody or t.orelse):
                    nd += 1
            return "TASK" if (raises or nd) else "QUESTION"
    return "notfound"

for rel_path in sorted(universe):
    if rel_path.name.startswith("_"):
        continue
    for lineno, name in _find_offenders(
        source=sources[rel_path], rel_path=rel_path,
        commands_trees=config.commands_trees,
        public_names=frozenset(n for p, n in public if p == rel_path),
        no_expected_failure_mode=frozenset(n for p, n in total if p == rel_path),
        supervisor_entry_files=config.supervisor_entry_files,
    ):
        print(classify(sources[rel_path], name), f"{rel_path}:{lineno}", name)
```

**Control:** `notfound` was 0 in all nine members — every convicted name resolved
to a parsed top-level function, so the classifier saw the same set the check did.

⚠️ Every figure here has a date. Re-derive before acting.

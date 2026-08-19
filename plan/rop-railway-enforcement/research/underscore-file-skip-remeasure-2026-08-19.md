# The `_`-file skip, re-measured fleet-wide 2026-08-19 — the costing evidence for `8zv3.5`

`8zv3.5` cannot be decided on the 2026-08-04 numbers: this track's own standing
rule is **re-measure before believing a figure**, and the fleet has moved 15 days
since. This note re-derives both bases from scratch.

## Method — stated so the numbers can be attacked

A harness replicates the shipped `_scan()` over the **decoupled** universe
(`resolve_check_universe()`), toggling **only** the `_`-prefixed FILE skip.
Everything else is the shipped criterion, imported from the shipped modules
rather than reimplemented: `_find_offenders`, `repo_local_public_names`,
`declared_public_names`, `functions_without_expected_failure_mode`,
`declared_absence_names`, `declared_variant_names`, and each repo's own
`load_config`. Each repo measured in its own checkout, at its current tip, under
its own pinned `livespec-dev-tooling`.

⚠️ **The harness is reproduced below rather than committed as a `.py`.** A file under
`plan/` is still first-party Python: it enters `resolve_check_universe()` and becomes
subject to every Python gate — lint, `__all__` coverage, per-file coverage — and to
**this very check**, which would make the measuring instrument an offender in its own
measurement. The commit gate caught that; it is recorded here because the next person
to write a research script will hit it too.

```python
# Run from each repo root: uv run --no-sync python measure.py
from pathlib import Path
from livespec_dev_tooling.checks.public_api_result_typed import _find_offenders
from livespec_dev_tooling.checks._public_api_consumption import (
    repo_local_public_names, declared_public_names)
from livespec_dev_tooling.checks._no_expected_failure_mode import (
    functions_without_expected_failure_mode)
from livespec_dev_tooling.checks._declared_absence_returns import declared_absence_names
from livespec_dev_tooling.checks._single_meaning_variants import declared_variant_names
from livespec_dev_tooling.config import load_config, resolve_check_universe

def measure(*, skip_underscore_files):
    cwd = Path.cwd()
    config = load_config(repo_root=cwd)
    root, universe = resolve_check_universe()
    sources = {rel: (root / rel).read_text(encoding="utf-8") for rel in universe}
    public = repo_local_public_names(sources=sources) | declared_public_names(
        declared=config.cross_repo_public_api, sources=sources)
    total = functions_without_expected_failure_mode(
        sources=sources, io_trees=config.io_trees)
    total |= declared_absence_names(
        declared=config.total_absence_returns, sources=sources)
    total |= declared_variant_names(
        declared=config.single_meaning_variants, sources=sources,
        io_trees=config.io_trees)
    out = []
    for rel_path in sorted(universe):
        if skip_underscore_files and rel_path.name.startswith("_"):
            continue
        for lineno, name in _find_offenders(
            source=sources[rel_path],
            rel_path=rel_path,
            commands_trees=config.commands_trees,
            public_names=frozenset(n for p, n in public if p == rel_path),
            no_expected_failure_mode=frozenset(n for p, n in total if p == rel_path),
            supervisor_entry_files=config.supervisor_entry_files,
        ):
            out.append((rel_path, lineno, name))
    return out
```

**So the only variable between the two columns is the skip.** Note this measures
the DECOUPLED universe in both columns — it is not a measure of what the shipped,
still-gated check convicts today, which is **zero everywhere** (see
`state-correction-2026-08-19.md`).

## MEASURED — all nine members, 2026-08-19

| member | universe | WITH skip (shipped) | WITHOUT skip | Δ attributable to the skip |
|---|---:|---:|---:|---:|
| `livespec-overseer` | 281 | 156 | 360 | **+204** |
| `livespec-orchestrator-beads-fabro` | 199 | 19 | 174 | **+155** |
| `livespec` | 165 | 14 | 23 | +9 |
| `livespec-dev-tooling` | 191 | 3 | 11 | +8 |
| `livespec-driver-codex` | 13 | 3 | 12 | +9 |
| `livespec-orchestrator-git-jsonl` | 50 | 4 | 6 | +2 |
| `livespec-runtime` | 39 | 15 | 15 | 0 |
| `livespec-driver-claude` | 10 | 0 | 0 | 0 |
| `livespec-console-beads-fabro` | 2 | 0 | 0 | 0 |
| **TOTAL** | **950** | **214** | **601** | **+387** |

Arithmetic carried rather than asserted: `214 = 156+19+14+3+3+4+15`,
`601 = 360+174+23+11+12+6+15`, `387 = 204+155+9+8+9+2`, `950 = 281+199+165+191+13+50+39+10+2`.

## ▶️ THE RATIO HELD; THE MAGNITUDES DID NOT

| basis | 2026-08-04 (ledger) | 2026-08-19 (this note) |
|---|---:|---:|
| WITH the skip | 160 | **214** |
| WITHOUT the skip | 446 | **601** |
| multiplier | 2.79x | **2.81x** |

**The 2.8x is stable and is the number the decision turns on.** The absolute
figures are NOT: both bases grew ~34% in fifteen days. Quote 214/601, and say the
date — a part and a total from different days do not add.

⚠️ **Two per-repo figures on `8zv3.5` are now stale and should be restated:**
`livespec-orchestrator-beads-fabro` was recorded 17 → 157, measures **19 → 174**;
`livespec-overseer` was recorded 115 → 249, measures **156 → 360**.

## The honest DISTINCT figure, because overseer double-counts

`livespec-overseer` mirrors `overseer/*.py` into `.claude-plugin/overseer/*.py`,
and `just check-codex-plugin-runnable-launcher` enforces the identity, so the
copies convert for free. Measured split:

| basis | overseer total | `overseer/` etc. | `.claude-plugin/` mirror |
|---|---:|---:|---:|
| WITH skip | 156 | 85 | 71 |
| WITHOUT skip | 360 | 187 | 173 |

**So the DISTINCT fleet conversion sites are 143 (with the skip) and 428
(without)** — `214 − 71` and `601 − 173`.

Worth noting rather than smoothing over: the mirror is **14 short of the primary
in both columns** (85 vs 71, 187 vs 173). The identity check covers 44 files, not
the whole tree, so "the copies convert for free" holds only for the mirrored
subset. **Do not budget overseer as exactly half.**

## What this does to the decision

`livespec-driver-codex` is the sharpest small case: **3 → 12**, so the skip hides
**75%** of its offenders in a 13-file universe. `livespec-runtime` is the
control — **15 → 15**, zero delta — which is what a repo with no `_`-prefixed
files in its universe should show, and it confirms the toggle is doing what it
claims rather than moving numbers indiscriminately.

Two repos carry **93%** of the entire delta (`overseer` 204 + `beads-fabro` 155 =
359 of 387). **So dropping the skip is not a uniform 2.8x tax — it is
concentrated, and it can be sequenced per repo.** Six of nine members move by 9
or fewer.

▶️ Combined with the ratified-text finding in `state-correction-2026-08-19.md`
(clause 0 binds `_`-prefixed NAMES, not FILES; `commands/_config.py` is imported
by 17 non-test product modules; `8o8e.21` already converted that file's
functions), the recommendation stands: **drop the skip, and take the two heavy
repos as their own sequenced units rather than as part of a fleet-wide wave.**

## ADDENDUM — the ratified text does not AUTHORISE a file skip

> ⚠️ **WORDING CORRECTED 2026-08-19.** This section originally read *"does not merely omit
> a file skip, it CONTRADICTS one"*, and argued it from §"Module API surface"'s
> every-module `__all__` requirement. **That overstates the case**: that sentence is
> scoped, in its own words, to `.claude-plugin/scripts/livespec/**`, so reading it as a
> fleet-wide statement about `_`-prefixed modules is a stretch. **"Does not authorise" is
> the defensible verb.** The weaker claim is still fatal for a skip that removes 387
> functions from a rule's reach, but it is a different claim and the panel should have the
> honest one. Self-caught while writing `8zv3-5-counter-case-2026-08-19.md`; see Counter 2
> there.

The §5 argument in `state-correction-2026-08-19.md` was that clause 0 binds NAMES
and nothing ratifies a FILE skip. That is an argument from ABSENCE. There is a
stronger, POSITIVE one, and it should be the one put to the maintainer.

**1. The adopted definition is name-shaped, verbatim.** Clause 0 adopts "the
private-helper definition in §'Typechecker rule set'". That section defines it
exactly once:

> *"Private helpers (**single-leading-underscore prefix or not in `__all__`**)
> SHOULD be annotated."*

It quantifies over **functions and dataclass fields**. There is no module- or
file-level clause anywhere in the section.

**2. §"Module API surface" AFFIRMATIVELY REQUIRES `_`-prefixed modules to declare
public API:**

> *"**Every** module ... MUST declare a module-top `__all__: list[str]` listing
> the public API names ... private helpers (single-leading-underscore prefix)
> MUST NOT appear in `__all__`."*

**"Every module" admits no exception for a `_`-prefixed one.** If a `_`-prefixed
FILE had no public API by definition, that requirement would be vacuous for every
such module — and the same sentence's private-helper carve-out is again about
NAMES within the module, not about the module's own name.

**3. And the fleet complies with it.** `commands/_config.py` declares:

```python
__all__: list[str] = [
    "FactoryTarget", "resolve_credential_wrapper", "resolve_fabro_bin",
    "resolve_fabro_factory", "resolve_fabro_sandbox_image", "resolve_store_config",
]
```

Six public names, none `_`-prefixed, in a `_`-prefixed file — declared exactly as
the ratified rule requires, consumed by 17 non-test product modules, and **never
once looked at by the check that governs them.**

▶️ **So the shipped file skip has no authority in the ratified text** — and the
`__all__` evidence above, read at its scoped strength, shows the fleet treating
`_`-prefixed modules as carrying public API rather than as private by construction. A module the spec compels to publish a
public API surface cannot coherently be treated as having none. That is the case
to put to the maintainer, and it does not depend on the 2.8x costing at all —
the costing says how much the fix is worth, not whether it is right.

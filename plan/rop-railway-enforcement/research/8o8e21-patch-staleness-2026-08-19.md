# `8o8e.21`'s patch, two weeks later — it does not apply, and the reason matters

The triage note called `8o8e.21` the cheapest of the eleven to dispose, and flagged one
thing as **unverified**: whether its authored Green patch still applies after two weeks
of drift. This resolves that. **It does not apply** — and the reason is worth more than
the answer.

## Measured, against `livespec-orchestrator-beads-fabro` master

Nothing was written to that repo; every result below is from `git apply --check`
(and `-3 --check`), which mutates nothing. It is a peer lane and not mine to dirty.

| file | plain apply | 3-way apply |
|---|---|---|
| `errors.py` | fails | **clean** |
| `commands/_dispatcher_credentials.py` | fails | **clean** |
| `tests/.../test_config.py` | fails at `:24` | **clean** |
| `commands/_config.py` | fails at `:61` | **CONFLICTS** |

So three of four resolve under a 3-way merge; the plain-apply failures on those three are
ordinary import-block drift. **One file genuinely conflicts.**

## ⛔ The conflict is not cosmetic — the module REGREW THE DEFECT

`_config.py` gained two public functions since the patch was authored, both now in
`__all__`:

```python
def has_fabro_factory(*, cwd: Path, factory: str) -> bool:
    block = _read_dispatcher_block(cwd=cwd)
    factories_raw = block.get("factories")
    ...

def has_fabro_factories(*, cwd: Path) -> bool:
    block = _read_dispatcher_block(cwd=cwd)
    factories_raw = block.get("factories")
    return isinstance(factories_raw, dict)
```

**The patch changes `_read_dispatcher_block` to return
`IOResult[dict[str, Any], ConfigUnreadable]`. An `IOResult` has no `.get()`.** Landing the
patch as-is breaks both functions.

▶️ **And look at what those two functions DO on an unreadable config: they return
`False`.** That is precisely the read-vs-write swallow `8o8e.21` exists to eliminate — an
unreadable `.livespec.jsonc` reported as "no such factory" rather than as a broken
config. **The defect propagated into two new public functions while its fix sat
unlanded.**

## The lesson, which generalises past this patch

**An unlanded fix does not merely go stale — the defect it fixes KEEPS BREEDING in code
written in the meantime.** Two weeks bought two new instances of the exact swallow, in the
exact module, written by people who had no reason to know a fix existed in a plan
directory in another repo.

⚠️ **This is the same failure shape as the rest of this track**, and it deserves to be
seen as such: a correct answer that is recorded somewhere non-authoritative does not
propagate. The Green patch was authored, gate-passed, and parked in
`plan/rop-railway-enforcement/research/` — a research directory in `livespec-dev-tooling`,
governing code in `livespec-orchestrator-beads-fabro`. **Nothing about that location makes
it reachable by anyone editing the module it fixes.**

## What this changes for the disposal

`8o8e.21` is **still the cheapest of the eleven**, and still a bug rather than a
conversion — so still unblocked by the deferred `8zv3.5` ruling. But it is **larger than
"land the patch"**:

1. 3-way apply the three clean files.
2. Hand-resolve `_config.py`'s import block (the patch adds
   `from dataclasses import dataclass`, which now already exists).
3. **Adapt `has_fabro_factory` and `has_fabro_factories`** to the new `IOResult` seam —
   and decide, per function, whether an unreadable config should read as `False` or
   propagate. Judging by the item's own reasoning it should propagate, but **that is the
   maintainer's call, not the patch's**, because it changes two public functions' contracts.
4. Re-run the Red→Green pair; the recorded trailers do not carry over to a re-resolved
   patch.

**Estimate honestly: this is no longer a patch-apply. It is a small implementation task
with a contract decision inside it.**

## Not done here

Nothing was applied, staged, or written to `livespec-orchestrator-beads-fabro`. This
session holds no worktree there, and the two contract questions in step 3 are the
maintainer's.

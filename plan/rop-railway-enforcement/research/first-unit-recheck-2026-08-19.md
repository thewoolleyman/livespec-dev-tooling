# The recommended first unit, rechecked — 2 of its 3 offenders are the `8o8e.28` class

Across several handoffs I recommended `livespec-driver-codex` as the first remediation
unit, on the grounds that it is *"3 offenders, one file, nothing undecided."* **I never
verified the last clause.** Twice this session an unverified recommendation of mine turned
out wrong, so I checked this one. **It is wrong too.**

## The three offenders, read

All in `dev-tooling/codex_hook_cache_reconcile.py`:

```python
def codex_home(*, override: str | None = None) -> Path:            # :72
    if override:
        return Path(override).expanduser()
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser()

def state_file(*, override: str | None = None) -> Path:            # :89
    ...env reads, path joins, no failure path...

def reconcile(*, root: Path, state_path: Path) -> Report:          # :152
    ...real failures, already expressed as Report(ok=False, problems=(...))...
```

`codex_home` and `state_file` are **pure path computations over environment reads. Neither
has any expected failure mode at all.** Converting them to `Result` manufactures precisely
the uninhabited failure track measured 19 times over in
`dead-failure-tracks-2026-08-19.md`.

## ⛔ THE MINIMAL PAIR — the conviction tracks I/O CONTACT, not failure possibility

The same file contains the control, and it is decisive. Measured against the shipped v179
analyser (`functions_without_expected_failure_mode`):

| function | returns | touches env? | v179-exempt | convicted |
|---|---|---|---|---|
| `cache_root` | `Path` | **no** — pure joins | **True** | no |
| `codex_home` | `Path` | **yes** — `os.environ`, `Path.home()` | False | **yes** |
| `state_file` | `Path` | **yes** — `os.environ`, `Path.home()` | False | **yes** |
| `reconcile` | `Report` | yes | False | **yes** |

`cache_root` and `codex_home` return the same type, are equally total, and sit in the same
module. **The only difference is that one reads the environment.** That difference alone
decides conviction.

▶️ **So `codex_home` and `state_file` are convicted for TOUCHING I/O while having NOTHING
TO PUT ON THE FAILURE TRACK.** That is `8o8e.28`'s family exactly — total by nature,
convicted by I/O contact — and `8o8e.28` is an OPEN QUESTION the maintainer has not priced.
(`io_trees = ()` in this repo, so no declaration is softening anything here.)

## `reconcile` is the one real conversion — and even it has an alternative

`reconcile` genuinely has failure modes, and already expresses them as a **hand-rolled
result type**: `Report(ok=False, current_version=..., problems=(...))`. That is the shape
the railway exists to replace, so converting it is meaningful work.

But it is also a candidate for the ratified `single_meaning_variants` carrier (v183) — a
closed discriminated union at a rendering boundary, declared rather than converted. **Which
route is right is a judgment, not a mechanical step.**

## ⛔ THE RECOMMENDATION I REPEATED IS WITHDRAWN

`livespec-driver-codex` is **not** "3 offenders, nothing undecided." It is:

- **2 offenders that cannot be honestly converted** without manufacturing dead failure
  tracks, pending the `8o8e.28` ruling; and
- **1 offender that is real work with a declare-or-convert choice inside it.**

**Its 3 is not cheaper than `git-jsonl`'s 4 — it is the same trap I warned about for
git-jsonl, and I walked into it while pointing at the other one.** I flagged git-jsonl's
`discover_merge_sha` and `resolve_canonical_branch` as carrying open questions and called
driver-codex clean by contrast. Both repos are majority-open-question.

## What the first unit actually should be

**Unknown, and it should be selected by MEASURE rather than by count.** The right filter
is not "fewest offenders" but "most offenders that are v179-non-exempt AND have a real
failure mode AND are not already a hand-rolled result type." Nothing in this plan has
computed that yet.

⚠️ **Until it is computed, no repo should be called the cheapest first unit.** The counts
in `shipped-basis-offender-inventory-2026-08-19.md` are counts of CONVICTIONS, and this
note shows convictions and convertible work are different sets. **Every "N offenders"
figure in this plan is an upper bound on real work, by an unmeasured margin.**

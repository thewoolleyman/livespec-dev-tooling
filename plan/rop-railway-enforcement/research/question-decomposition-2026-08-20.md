# The 223 questions decompose into FOUR classes — and 101 of them already have a
# ratified mechanism nobody has used

`task-vs-question-census-2026-08-20.md` established that 223 of 234 shipped-basis
convictions are QUESTIONS rather than TASKS, and that the 11 tasks reduce to five
blocked functions. That leaves the real remaining decision: **a disposition
policy for the questions.** "Convert them" is not well-formed — they originate no
expected failure — so the policy has to say what each SHAPE gets.

This note decomposes the bucket so the policy can be written per-class instead of
per-function. Measured 2026-08-20, shipped basis, same harness as the census plus
a shape classifier.

## The decomposition

| class | overseer | beads-fabro | livespec | runtime | git-jsonl | codex | **fleet** |
|---|---:|---:|---:|---:|---:|---:|---:|
| **declared-absence** (`X \| None`) | 64 | 0 | 0 | 3 | 2 | 0 | **69** |
| **io-total** (public, does IO, no failure) | 50 | 3 | 6 | 3 | 1 | 2 | **65** |
| **pure-total** (public, pure, no failure) | 38 | 5 | 6 | 6 | 1 | 1 | **57** |
| **entrypoint `main()`** | 20 | 9 | 2 | 1 | 0 | 0 | **32** |
| **total** | 172 | 17 | 14 | 13 | 4 | 3 | **223** |

**69 + 65 + 57 + 32 = 223.** Re-added here, not carried; it reconciles with the
census exactly.

⚠️ The `X | None` detector is deliberately STRUCTURAL, not a substring test: only
a top-level `X | None` or `Optional[X]` return annotation counts. A substring test
over-counted by 6 (it caught `Callable[..., None]` and similar). **69 is the
strict number; 75 was the loose one.** Quote 69.

## ⛔ THE FINDING: 101 OF THE 223 (45%) ALREADY HAVE A RATIFIED MECHANISM

### `total_absence_returns` — the exact relief for the largest class, **used ZERO
times in all nine repos**

`_declared_absence_returns.py` (v179 member 2) exists precisely because member 1
"refuses the whole `X | None` shape ... because whether a `None` models a FAILURE
or a legitimate ABSENCE is a semantic question no AST can answer." The declared
relief is: name the function in the `total_absence_returns` role key **with a
written reason**, and `public_api_result_typed` treats it as outside the
Result-return rule.

**Fleet-wide declaration count: 0.** So does its sibling `single_meaning_variants`.

▶️ **69 convictions sit in exactly the shape a shipped, ratified key exists to
relieve, and the key has never been used once.** That is not a conversion backlog;
it is 69 per-function judgments ("is this `None` an ABSENCE or a FAILURE?") plus a
written reason each. The key is REMOVING-polarity — an absent declaration is the
strict end — so nothing is unsafe today; the cost is that 69 functions are counted
as debt that the ratified text may never have intended as debt.

⚠️ Its bounds are hard-fail, not warnings: bound 1 rejects a declared entry whose
function is not `X | None`, bound 3 rejects one that no longer resolves. So the
declarations must be authored against DEFINITIONS, not imports — the failure mode
that bit `cross_repo_public_api` on its first day.

### `supervisor_entry_files` — used, but not covering the 32 `main()`s

Every repo declares some (1–5). The 32 convicted `main()`s are outside them, and
the class is MIXED — this is the part that does not generalize:

- **beads-fabro's 9** are almost entirely NOT product: six `dev-tooling/checks/*.py`
  check scripts, two `plan/.../rehearsal-package/wrappers/*.py` scratch wrappers,
  one hook. ▶️ These fold into **open maintainer question 4** (the non-product-in-
  universe class) rather than needing a new answer.
- **overseer's 20 are 10 REAL product CLI entrypoints doubled by the mirror.**
  Those are a genuine entry-point question.

## ▶️ SO THE POLICY HAS TO ANSWER ONLY TWO NEW THINGS

**122 of 223 (55%) — the io-total and pure-total classes — are the genuinely new
ruling**, and they are one question asked twice: *what does the rule require of a
PUBLIC function that has NO expected failure mode?* Three candidate answers:

1. `IOResult[X, Never]` / `Result[X, Never]` — honest about "cannot fail", but 122
   signature changes that add no failure track and no caller obligation.
2. Extend the `no_expected_failure_mode` exemption to cover them. ⚠️ It ALREADY
   exists and already exempts some functions — `read_thread_names` in overseer is
   exempt while `proc_fd_targets` beside it is not. **Understanding why it fires
   for one and not the other is the cheapest next investigation on this track**,
   and it is `8o8e.30`/`.31` territory.
3. Rule that the Result-return requirement binds only functions with an expected
   failure mode — the narrowest reading, and the one the TASK/QUESTION split
   suggests the ratified text may already mean.

**The remaining 101 need no new rule at all** — 69 want an unused key exercised,
32 want the universe question already open as #4.

⚠️ `8zv3.5` changes the SIZE of every number here (234 → ~601) but not the
SHAPE. The four classes and the two questions are the same either way.

## The classifier

Shipped as a fenced block, not a `.py`: a file under `plan/` enters
`resolve_check_universe()` and would be measured by its own harness. It runs over
the census's offender set and buckets the QUESTION half.

```python
_IO_CALLS = {"run", "check_output", "Popen", "open", "read_text", "read_bytes",
             "write_text", "write_bytes", "iterdir", "rglob", "glob", "exists",
             "mkdir", "unlink", "stat", "readlink", "is_file", "is_dir"}
_IO_MODULES = {"subprocess", "os", "shutil", "socket", "urllib"}

def touches_io(fn):
    for n in ast.walk(fn):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Attribute) and f.attr in _IO_CALLS:
                return True
            if isinstance(f, ast.Name) and f.id == "open":
                return True
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) \
                and n.value.id in _IO_MODULES:
            return True
    return False

def returns_optional(fn):
    """Only a TOP-LEVEL `X | None` / `Optional[X]` — never a substring test."""
    ann = fn.returns
    if ann is None:
        return False
    if isinstance(ann, ast.BinOp) and isinstance(ann.op, ast.BitOr):
        return any(isinstance(s, ast.Constant) and s.value is None
                   for s in (ann.left, ann.right))
    if isinstance(ann, ast.Subscript):
        return isinstance(ann.value, ast.Name) and ann.value.id == "Optional"
    return False

# bucket order matters: main() first, then declared-absence, then io, then pure
```

⚠️ `touches_io` is a NAME-based heuristic: it cannot see IO reached through an
injected seam, so the io-total count is a FLOOR and the pure-total count a
CEILING. The split between those two classes is indicative; their SUM (122) is
the number the ruling has to cover, and that sum is exact.

⚠️ Every figure here has a date. Re-derive before acting.

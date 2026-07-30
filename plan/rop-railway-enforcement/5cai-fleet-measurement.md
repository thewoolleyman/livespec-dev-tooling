# `5cai` — the fleet's cross-member consumption graph, measured

**Taken 2026-07-30** against all nine members' **master tarballs** from the forge
(no shared clone touched), using the shipped slice-1 primitive
(`FleetContext.member_tree_snapshot`) and the slice-2 oracle
(`fleet/_member_sources.py` + `fleet/_public_api_graph.py`).

**Nine members read, 0 skipped, 0 unparsed.** That matters as much as the
findings: a verdict of "nothing found" over a fleet that was never read is this
thread's signature failure, so the coverage is stated before the result.

This file exists because these lists are the most expensive facts the
pre-registration measurement produced, and they were about to live only in a
terminal pane.

---

## ▶️ THE VERDICT: 58 edges, and the row convicts exactly TWO members

| member | declared | undeclared functions | consumption sites |
|---|---|---|---|
| `livespec-dev-tooling` | 4 | **9** | 12 |
| `livespec-runtime` | 0 | **11** | 23 |
| the other seven | 0 | **0** | 0 |

The criterion, stated so the lists are legible: a member is in breach when a
name it defines is **consumed by another member**, is **not declared** in its
`cross_repo_public_api`, and is **not already public by a repo-LOCAL v178
form**. The third clause is load-bearing — a name the local check already
scopes needs no declaration, and reporting it would manufacture work.

### `livespec-dev-tooling` — 9 functions, 12 sites

Every one is `checks/<slug>.py::main`:

| function | consumed by |
|---|---|
| `checks/all_declared.py::main` | beads-fabro + runtime test trees |
| `checks/assert_never_exhaustiveness.py::main` | runtime test tree |
| `checks/keyword_only_args.py::main` | beads-fabro + runtime test trees |
| `checks/main_guard.py::main` | beads-fabro test tree |
| `checks/no_inheritance.py::main` | beads-fabro + runtime test trees |
| `checks/no_lloc_soft_warnings.py::main` | beads-fabro test tree |
| `checks/no_write_direct.py::main` | beads-fabro test tree |
| `checks/private_calls.py::main` | beads-fabro test tree |
| `checks/wrapper_shape.py::main` | beads-fabro test tree |

### `livespec-runtime` — 11 functions, 23 sites, and it declares NOTHING

| function | consumed by |
|---|---|
| `credentials.py::decide_credentials` | beads-fabro `bin/_bootstrap.py` |
| `credentials.py::wrapper_launch_failure` | beads-fabro `bin/_bootstrap.py` |
| `cross_repo/types.py::parse_cross_repo_manifest` | beads-fabro, git-jsonl, **livespec** |
| `work_items/lifecycle.py::is_item_ready` | beads-fabro ×3 |
| `work_items/lifecycle.py::lane_of` | beads-fabro ×2, git-jsonl |
| `work_items/rank.py::key_between` | beads-fabro ×2, git-jsonl |
| `work_items/rank.py::n_keys_between` | beads-fabro ×3 |
| `work_items/reduce.py::materialize_work_items` | beads-fabro, git-jsonl |
| `work_items/reduce.py::random_id_suffix` | beads-fabro, git-jsonl |
| `work_items/reduce.py::reduce_work_item_heads` | git-jsonl |
| `work_items/reduce.py::work_item_record_identity` | git-jsonl |

**These are PRODUCT imports (clause 1), not test imports** — `store.py`,
`_ids.py`, `commands/*.py`. The blast radius of a conversion there is the
`dx8l` shape exactly.

---

## ⛔ THE 9 ARE CLAUSE-2 SYMBOL IMPORTS, NOT CLAUSE-3 PROCESS ENTRY POINTS

Asked because the two clauses have different consequences and `main` is a name
that invites the wrong assumption. **Answered by reading both consumers, not by
inferring from the name.** Both do:

```python
from livespec_dev_tooling.checks import (all_declared, keyword_only_args, ...)
...
assert wrapper_shape.main() == 0
```

They import the SUBMODULE and reach `.main` as a callable value, then **call it
IN-PROCESS**. That is v178 clause 2 (cross-repo test import), resolved through
`attribute_reaches`. beads-fabro's file also contains
`assert "python -m livespec_dev_tooling.checks.wrapper_shape" in justfile` —
a STRING assertion ABOUT the justfile, not an invocation, and the only place
the process form appears at all.

**So this is NOT the known `main() -> int` location-scoping spec defect**, and
must not be filed as it. The consumers hold these functions as callables and
act on their return values, which is exactly the contract the Result-return
rule governs.

---

## 🔴 THE COLLISION REGISTRATION WOULD HIT, AND WHY IT IS MECHANICAL

Registering the row at error severity today fires BOTH blocking modes:

- **dev-tooling's OWN row fails** → `own_failing_rows` non-empty →
  `check-fleet-conformance` fails → **the registration PR's own CI fails**, so
  it cannot land. Not merely unwise: mechanically impossible.
- **`livespec-runtime`'s 11** → this repo's PRs stay GREEN, and the
  **scheduled sweep and release fan-out preflight break fleet-wide** on the
  next release. Worse, and easier to miss for exactly that reason.

Hence REMEDIATE-THEN-FLIP (this repo's own ratified v034 carve-out 1). The row
keeps **error** severity and ships INERT — the Phase 3 shape — and registration
is the follow-up that makes it gate.

**AND THE REMEDIATION HAS ITS OWN TRAP.** Declaring dev-tooling's 9 makes them
public for `public_api_result_typed`, taking **this repo's ratified-rule count
from 0 to 9** unless each file also earns a `supervisor_entry_files` entry.
That is the arming gate's "count is zero" precondition colliding with 5cai's
remediation — the fourth spelling of this thread's ordering trap.

**⛔ THE ONE RESOLUTION THAT IS FORBIDDEN: under-declaring
`cross_repo_public_api` to keep the count at zero.** Omitting a genuinely
consumed name to protect a number is `pure_trees = []` in a new costume, at the
end of the epic that removed it — and `5cai` would convict dev-tooling for
precisely that, which is the row working on its own author. **If the honest
resolution leaves the count non-zero, ARMING WAITS and the gate gets
restated.** A clean number bought by an incomplete declaration is not an
acceptable outcome; a delayed arming is.

Each `supervisor_entry_files` entry must be judged PER FILE against what that
file actually does, with a written reason naming its specific write contract —
the shape the five existing entries and class B's nine already use. Where an
exemption is unwarranted, say so and do not take it. Nine at once with no
per-file judgement is the bulk-declaration hazard; nine reasoned entries is
not.

---

## 🐛 TWO DEFECTS THE MEASUREMENT FOUND IN THE ORACLE ITSELF

The first run reported **54** undeclared consumptions. **19 were false**, in two
classes — which is the whole argument for measuring before registering rather
than after.

- **14 from ONE byte-identical installed file.** `livespec_footgun_guard.py`
  ships into most members as installed foreign content.
  `livespec-driver-codex` does `import livespec_footgun_guard` after a
  `sys.path` insert pointing at ITS OWN copy — verified by reading that test
  and that repo's tree — and the bare dotted suffix matched every member's
  copy. Python resolves that import to the copy on the path, so nothing crosses
  a boundary. The oracle reported one against SEVEN members for a file none of
  their consumers ever opens.
- **5 from clause 0.** `_check_segment`, `_decision`, `_strip_jsonc_comments` —
  v178 keeps the `_`-prefix disqualifier.

**Both ran in the OVER-enforcing direction**, which is the direction that
discredits a row on its first real run. Fixed in
`fix(fleet): a member that satisfies an import itself crosses no boundary`.
The ambiguity flag was working correctly throughout — all 14 false findings
carried it — which is what made them legible in the first output. Reporting
doubt is not the same as resolving it.

---

## 📐 App installation pool, measured (`mmqe`)

Installation **131208965**, across the window that reset at **16:48:24Z** —
which spans **two** releases (v1.10.0 at 15:55, v1.11.0 at 16:43):

| time (UTC) | used | remaining |
|---|---|---|
| 16:35:54 | 303 | 4697 |
| 16:38:48 | 330 | 4670 |
| 16:43:16 | 434 | 4566 |
| **16:46:16** | **532** | **4468** ← window peak |
| 16:48:24 | *window reset* | |
| 16:49:19 | 0 | 5000 |
| 17:04:35 | 77 | 4923 |

**Peak 532 of 5000 — 10.6%.** Two releases, their fan-outs and six
`check-fleet-conformance` jobs together spent about a tenth of the budget. The
pool did not approach exhaustion, and an independent all-green sample of the
SAME window agrees.

**So cumulative core exhaustion is unlikely to be the mechanism**, and the
next hypothesis is a **secondary rate limit** (burst/concurrency abuse
detection). It fits the evidence in the way the core-pool story does not:
GitHub returns 403 with rate-limit wording for secondary limits, and
**they do not move `used`** — which is why every retrospective look at the
counter has found nothing.

**Falsifiable, and cheaper than another window:** a secondary-limit 403 carries
`Retry-After` and/or "exceeded a secondary rate limit" in the body, where core
exhaustion carries `x-ratelimit-remaining: 0`. **Capture the response HEADERS
on the next instance, not the counter.** One window is one window; this is a
number, not a verdict, and it disagrees with the drain story.

The probe that took these is `pool_probe.py` — app JWT → installation token →
`GET /rate_limit`, which does not itself consume quota (two consecutive reads
showed 303 → 303).

# The Red leg does NOT enforce the coverage floor — the 2026-08-23 refusal was a staged-shape error

**Measured 2026-08-23, `livespec` at `82d6bcf1`, `livespec-dev-tooling` at `6dff8c1e`.**

## What the previous session recorded, and what is actually true

The 2026-08-23T19:21Z handoff on `livespec-dev-tooling-8o8e` stopped `8o8e.25` on this
diagnosis:

> "`livespec`'s commit gate runs the FULL aggregate including a **100% coverage floor**, on
> BOTH legs. … ▶️ **THIS IS A GENUINE CONFLICT between two ratified mechanisms** — the
> Red→Green ritual requires a failing test-only commit, and the 100% floor requires every
> line covered by the tests in that same commit."

⛔ **There is no conflict.** The Red leg is *explicitly exempted* from the coverage floor,
and has been all along. `livespec`'s `justfile` `check-pre-commit` recipe:

```bash
if [[ "$test_count" -eq 1 ]] && [[ "$impl_count" -eq 0 ]]; then
    echo ":: Red-mode shape detected: $test_staged"
    echo ":: skipping coverage gates (commit-msg replay hook is the verifier; coverage runs at Green amend)"
    SKIP_TARGETS="check-coverage check-per-file-coverage" just check
    exit $?
fi
```

`lefthook.yml` says the same thing in prose at the top of the file: *"the heavy `just
check-pre-commit` aggregate (Red-mode-aware — skips check-coverage when the staged tree
matches the Red commit shape)."*

## The real cause: `test_count -eq 1`

**Red mode is EXACTLY ONE staged test file and ZERO staged impl files.** The refused attempt
staged TWO test files (`test_config_edit.py` and `test_editing.py`), so the Red-mode branch
was never taken, the full aggregate ran against **master's** impl, and coverage landed at
99%.

▶️ **This also explains the anomaly the handoff flagged as undiagnosed** — *"An earlier Red
for this same item PASSED (`20260823T184911Z-2337397`, test_config_edit alone). It broke
once `test_editing.py` joined the changeset."* One test file took the Red-mode branch; two
did not. The coverage number was a symptom, not the mechanism.

## The single-test-file rule is ratified twice, not incidental

Had coverage somehow passed, the commit-msg hook would have refused the same commit for the
same underlying reason. `livespec_dev_tooling/checks/_red_green_replay_modes.py`,
`_handle_red_mode`:

```python
if len(tests_paths) > 1:
    log.error(
        "multi-test-file: Red mode is per-file (one test file per commit)",
        check_id="red-green-replay-multi-test-file",
        hint=("The v034 D2 trailer schema's `TDD-Red-Test-File-Checksum:` is a "
              "singular field; stage exactly one test file per Red commit."),
    )
    return 1
```

⚠️ **So the two gates AGREE.** `check-pre-commit`'s `test_count -eq 1` is the same contract
the trailer schema encodes: `TDD-Red-Test-File-Checksum` is singular, so a Red carries
exactly one test file. Two mechanisms, one rule, no conflict.

## The resolution, and why the change split into two commits

Of the four files in `8o8e25-green-2026-08-23.patch`, the two `test_editing.py` additions
are **additive coverage tests for pre-existing behavior** — they exercise
`write_proposal_override`'s route through `_edit_result`, which the config change does not
touch. Measured: they **PASS unmodified against master's impl** (18 passed). They are not a
Red at all, and were only ever failing to land because they were riding in a Red commit.

| commit | staged | leg taken | trailers |
|---|---|---|---|
| 1 | `test_editing.py` alone (passes on master) | green-verified (`chore:` prefix, rule 3) | `TDD-Suite-Green-*` |
| 2 | `test_config_edit.py` alone (9 genuine assertion failures) → amend impl | Red → Green | `TDD-Red-*` + `TDD-Green-*` |

Both Red legs skipped coverage as designed; the Green amend ran the full aggregate
including the floor, which the complete change satisfies.

## 📜 The lesson, and it is this epic's own shape a fourth time

⚠️ **A gate that refuses for reason B while you are looking at symptom A will be diagnosed
as symptom A.** The coverage number was real, printed, and quantitative — 99% against a 100%
floor — and it was downstream of a shape rule that never printed anything, because the
branch that would have announced Red mode was simply not entered. Nothing said *"this is not
a Red"*; the aggregate just ran, as it does for every non-Red commit.

▶️ Three false constraints have now been retired from this thread by reading the mechanism
instead of the symptom: a check scanning zero files, a preservation warning over
already-preserved data, and now a mechanism conflict that was a staged-file count. **Each
one had blocked real work, and each cost minutes to disprove once someone read the source.**

⛔ **Do not quote "the Red leg enforces the coverage floor" from any earlier handoff.** It is
false, and the entries carrying it are superseded on that point by this note.

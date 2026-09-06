# Writing about template-interpolation syntax in ledger records

A work item whose own TEXT reproduces a literal doubled-brace
template-interpolation delimiter pair makes itself **undispatchable**. Dispatch
graph construction fails on an undefined template variable whose name appears
only in the item record and never in the workflow.

`check-work-item-interpolation-delimiters` enforces this. This page is the
convention that makes the check satisfiable: without it there would be no
conforming way to file an item *about* a workflow line, and every legitimate
record on the subject would be a violation.

## The mechanism

The escaper in the Dispatcher is correct but **self-cancelling**: rendering its
output once restores the original delimiter. Fabro renders the goal twice — file
inlining writes the rendered value back, and variable expansion then parses that
value again — so the restored delimiter meets a second parse. That is why the
failure survives an escaper that visibly runs.

## The convention

Never reproduce the literal pair. Write it with the substitution characters:

| Meaning                            | Write this | Codepoint |
| ---------------------------------- | ---------- | --------- |
| literal interpolation **opener**   | `⟦`        | U+27E6    |
| literal interpolation **closer**   | `⟧`        | U+27E7    |

Then put a short legend on the record so a reader knows the substitution is
deliberate and knows what the original text said:

```text
Delimiter legend: ⟦ = the literal template-interpolation opener,
⟧ = the literal closer. Substituted per docs/work-item-interpolation-delimiters.md.
```

A record that quotes a workflow line therefore reads
`runs-on: ⟦ vars.CI_RUNNER_LABELS ⟧` rather than reproducing the delimiters and
destroying itself.

## Two severities, two remedies

The check reports these as distinct verdicts because the remedies are not the
same:

- **`editable-repair-in-place`** — the pair sits in `title`, `description`,
  `design`, `acceptance_criteria`, `notes`, or `metadata`. Those fields are
  editable: rewrite the pair using the substitution characters, add the legend,
  and the record is clean.
- **`append-only-successor-or-hold`** — the pair sits in a **comment**. Comments
  are append-only and are assembled verbatim into future dispatch briefs, so the
  record is permanently poisoned. The remedy is a clean-text successor item or a
  non-dispatchable hold. It is **never** evidence deletion.

## Population and arming

The check scans **non-closed** records only. Closed items are excluded by
design: they are never dispatched, and historical records that predate this
convention still carry the pair. Scoping to non-closed is what makes arming
safe rather than a repeat of arming-ahead-of-adoption.

The check is **disarmed by default**. It self-skips unless both
`LIVESPEC_RUN_WORK_ITEM_INTERPOLATION_DELIMITERS` is truthy and
`BEADS_DOLT_PASSWORD` is present, so a credential-less `just check` never
self-gates on it.

**Arm it only after a measured sweep reports zero offenders among non-closed
items.** The sweep is the check itself, run once by hand:

```bash
/usr/local/bin/with-livespec-env.sh -- \
  env LIVESPEC_RUN_WORK_ITEM_INTERPOLATION_DELIMITERS=1 \
  just check-work-item-interpolation-delimiters
```

A non-zero exit lists every offender with its work-item id, its field, and its
verdict. Repair the editable ones, file successors for the comment ones, re-run
until the sweep is clean, and only then persist the lever.

An **empty** ledger read while armed is a failure, not a clean sweep: an armed
check inspecting nothing is a misconfiguration (usually a missing credential or
an unreachable tenant), and reporting it as a pass would be the fail-open this
check exists to remove.

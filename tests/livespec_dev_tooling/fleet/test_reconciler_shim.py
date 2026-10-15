"""Tests for `livespec_dev_tooling/fleet/_reconciler_shim.py`.

This module owns the acceptance assertion that the shim "invokes the reusable
reconciler workflow on master CI completion, on revert and fix-forward pull
request events, and on a schedule no coarser than five minutes" (work-item
`livespec-dev-tooling-dw7dzd`, child D of plan `red-master-self-healing`).

THE SHIM BODY IS PYTHON DATA, NOT A COMMITTED WORKFLOW FILE, and that is the
reason this assertion is assertable here at all. The factory dispatch
credential carries no `workflows` grant (livespec `.ai/ci-gate-discipline.md`
section "workflows boundary"), so a canonical shim stored under
`.github/workflows/` could neither be written by this change nor read back by a
test. Storing it as data is also what the three pin-and-bump shims already do
(`_reconcile_shims`), so this is the established home rather than a workaround:
the installer renders these bytes into a member, and the conformance row
compares a member's bytes against them.

ASSERTED STRUCTURALLY OVER THE TEXT, NOT THROUGH A YAML PARSE. No YAML library
is vendored in this repository, so `_on_triggers` cuts the `on:` block out of
the rendered body by indentation and the per-trigger assertions read the
inline-list values out of it. The alternative — asserting whole literal lines
of the body — would make the test a mirror of the implementation and would pass
for a body whose triggers had been reordered into something else entirely.

THE SCHEDULE BOUND IS COMPUTED RATHER THAN PATTERN-MATCHED. `_max_gap_minutes`
expands the cron minute field and measures the LARGEST gap between successive
firings across the hour boundary, so the assertion is the acceptance
assertion's own words — "no coarser than five minutes" — and not a match on
the literal `*/5` that happens to satisfy it today. A cron of `0,5 * * * *`
would pass a pattern match on "5" and leave the reconciler blind for 55
minutes of every hour.
"""

from __future__ import annotations

import importlib
import itertools
from pathlib import Path
from types import ModuleType

__all__: list[str] = []


_MODULE_NAME = "livespec_dev_tooling.fleet._reconciler_shim"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3] / "livespec_dev_tooling" / "fleet" / "_reconciler_shim.py"
)

_OWNER = "acme"
_REPO = "widget"


def _shim_module() -> ModuleType:
    """The canonical-shim module, asserting its existence BEFORE importing it.

    The `is_file` assertion is deliberately first: it is a genuine assertion
    that fails while the module is absent, where a top-level import of a
    missing module would die at COLLECTION and prove only unimportability.
    """
    assert (
        _MODULE_PATH.is_file()
    ), f"{_MODULE_PATH} does not exist — the canonical reconciler shim has no home"
    return importlib.import_module(_MODULE_NAME)


def _rendered_shim() -> str:
    """The canonical reconciler shim body rendered for one member."""
    module = _shim_module()
    return str(module.reconciler_shim_content(owner=_OWNER, repo=_REPO))


def _on_triggers(*, body: str) -> dict[str, str]:
    """The workflow body's `on:` block, as `{trigger name: its own text}`.

    Keys are the names at exactly two-space indent; each value is every line
    below that name until the next two-space-indent name or the end of the
    block. A trigger with no body of its own (`workflow_dispatch: {}`) maps to
    the remainder of its own line.
    """
    lines = body.splitlines()
    try:
        start = lines.index("on:") + 1
    except ValueError:  # pragma: no cover - the assertion below reports it
        return {}
    triggers: dict[str, str] = {}
    current = ""
    for line in lines[start:]:
        if line and not line.startswith(" "):
            break
        stripped = line.strip()
        if line.startswith("  ") and not line.startswith("   ") and ":" in stripped:
            current, _, inline = stripped.partition(":")
            triggers[current] = inline.strip()
            continue
        if current:
            triggers[current] = f"{triggers[current]}\n{stripped}".strip()
    return triggers


def _inline_list(*, text: str, key: str) -> frozenset[str]:
    """The members of an inline `key: [a, b, c]` list inside `text`."""
    for line in text.splitlines():
        prefix, _, rest = line.strip().partition(":")
        if prefix != key:
            continue
        return frozenset(
            item.strip() for item in rest.strip().strip("[]").split(",") if item.strip()
        )
    return frozenset()


def _minute_firings(*, minute_field: str) -> frozenset[int]:
    """Every minute of the hour a cron minute field fires on."""
    if minute_field == "*":
        return frozenset(range(60))
    firings: set[int] = set()
    for term in minute_field.split(","):
        step, _, divisor = term.partition("/")
        if divisor:
            firings.update(range(0, 60, int(divisor)))
            continue
        firings.add(int(step))
    return frozenset(firings)


def _max_gap_minutes(*, cron: str) -> int:
    """The largest gap in minutes between successive firings of `cron`.

    Measured ACROSS the hour boundary: the gap from the last firing of one hour
    to the first of the next is a real blind window, and a measure that stopped
    at minute 59 would report `0,5 * * * *` as a five-minute cadence.
    """
    firings = sorted(_minute_firings(minute_field=cron.split()[0]))
    assert firings, f"cron {cron!r} fires on no minute at all"
    wrapped = [*firings, firings[0] + 60]
    return max(later - earlier for earlier, later in itertools.pairwise(wrapped))


def test_the_trigger_reader_answers_nothing_rather_than_guessing() -> None:
    """The reader's own edges, so a silent misread cannot pass as a trigger set.

    Each case is a shape that would otherwise make the reader INVENT an answer:
    a body with no `on:` block at all, an `on:` block running to end-of-file
    with no `jobs:` to stop it, a blank line before the first trigger name, and
    a key the block does not carry. The reader answers emptily for each, which
    is what makes the per-trigger assertions below meaningful — an empty answer
    fails them, where a guessed one could satisfy them.
    """
    assert _on_triggers(body="name: x\njobs: {}\n") == {}
    assert _on_triggers(body="on:\n  schedule:\n    - cron: '*/5 * * * *'\n") == {
        "schedule": "- cron: '*/5 * * * *'"
    }
    assert _on_triggers(body="on:\n\n  workflow_dispatch: {}\njobs:\n") == {
        "workflow_dispatch": "{}"
    }
    assert _inline_list(text="types: [a, b]", key="workflows") == frozenset()


def test_the_gap_measure_sees_a_cadence_a_pattern_match_would_accept() -> None:
    """The measure itself, so the bound below cannot pass by being unmeasured.

    `0,5 * * * *` mentions a 5 and is 55 minutes coarse. A test asserting the
    shim's cron bound is only as good as the measure it asserts through, so the
    measure is exercised on that exact trap before it is trusted.
    """
    assert _max_gap_minutes(cron="*/5 * * * *") == 5
    assert _max_gap_minutes(cron="0,5 * * * *") == 55
    assert _max_gap_minutes(cron="* * * * *") == 1


def test_the_shim_runs_on_master_ci_completion() -> None:
    """`workflow_run` on the gating CI workflow, on completion.

    `completed` rather than a success/failure filter: the reconciler decides
    from recorded state, and a run that came back GREEN is what ends an
    episode and closes a superseded revert. Subscribing only to failures would
    leave that step waiting for the schedule.
    """
    triggers = _on_triggers(body=_rendered_shim())
    assert "workflow_run" in triggers, f"no workflow_run trigger in {sorted(triggers)}"
    block = triggers["workflow_run"]
    assert _inline_list(text=block, key="workflows") == frozenset({"CI"})
    assert _inline_list(text=block, key="types") == frozenset({"completed"})


def test_the_shim_runs_on_revert_and_fix_forward_pull_request_events() -> None:
    """The pull-request events a revert and a claimed fix-forward move through.

    `labeled`/`unlabeled` are the fix-forward CLAIM mechanism (the charter's
    "a label/comment on the revert PR naming the fix PR"); `synchronize` is a
    fix pushing a new commit; `closed` is the revert landing or the fix
    merging. `issue_comment` carries the comment half of the same claim, which
    `pull_request` does not deliver.
    """
    triggers = _on_triggers(body=_rendered_shim())
    assert "pull_request" in triggers, f"no pull_request trigger in {sorted(triggers)}"
    assert _inline_list(text=triggers["pull_request"], key="types") >= frozenset(
        {"opened", "reopened", "synchronize", "labeled", "unlabeled", "closed"}
    )
    assert "issue_comment" in triggers, f"no issue_comment trigger in {sorted(triggers)}"
    assert _inline_list(text=triggers["issue_comment"], key="types") >= frozenset({"created"})


def test_the_shim_schedule_is_no_coarser_than_five_minutes() -> None:
    """The schedule leg — deadline enforcement and missed-event cover."""
    triggers = _on_triggers(body=_rendered_shim())
    assert "schedule" in triggers, f"no schedule trigger in {sorted(triggers)}"
    crons = [
        line.partition("cron:")[2].strip().strip("'\"")
        for line in triggers["schedule"].splitlines()
        if "cron:" in line
    ]
    assert crons, f"schedule trigger carries no cron: {triggers['schedule']!r}"
    assert min(_max_gap_minutes(cron=cron) for cron in crons) <= 5


def test_the_shim_delegates_to_the_reusable_reconciler_workflow() -> None:
    """The shim is a SHIM: it carries triggers and a `uses:`, and no logic.

    Asserting that no job declares a `run:` step is the half that keeps it one.
    A shim that grew an inline step would be per-repo logic the conformance row
    could only report as drift, and every fleet member would carry its own copy.

    Scoped to the `jobs:` block and matched on a line that STARTS a `run:` key,
    because a bare `"run:" not in body` substring test is satisfied by the
    `workflow_run:` trigger this shim is required to have.
    """
    body = _rendered_shim()
    module = _shim_module()
    assert f"uses: {_OWNER}/livespec-dev-tooling/.github/workflows/" in body
    assert str(module.REUSABLE_WORKFLOW_FILE) in body
    assert "secrets: inherit" in body
    job_lines = body.partition("\njobs:\n")[2].splitlines()
    assert job_lines, "the shim declares no jobs block"
    assert not [line for line in job_lines if line.strip().startswith("run:")]


def test_the_shim_is_rendered_per_member_at_the_canonical_path() -> None:
    """The install path, and that rendering threads the member's own owner."""
    module = _shim_module()
    assert str(module.MASTER_HEALTH_WORKFLOW).startswith(".github/workflows/")
    assert "{owner}" not in _rendered_shim()
    assert "other-owner/livespec-dev-tooling" in str(
        module.reconciler_shim_content(owner="other-owner", repo=_REPO)
    )

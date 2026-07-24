"""Tests that the persisting-gap promotion is CONTEXT-SCOPED, not global.

Maintainer ruling (2026-07-24, `livespec-dh9r`): a persisting pin gap is
an ERROR only in the fan-out preflight context — where the `livespec-f73t`
per-member filter consumes it as a loud per-member exclusion and
propagation continues to every conformant sibling — and stays a WARNING
in ordinary per-PR CI context.

**Why the scoping is required.** `check-fleet-conformance` runs in CI in
`livespec-dev-tooling` ONLY (measured 2026-07-24: zero mentions in the
other eight members' `ci.yml`), plus the fan-out preflight. Promoted
globally, ANY member's persisting gap reddens `livespec-dev-tooling`'s own
per-PR CI — including the PRs that would repair the gap — while the
offending member is typically owned by a different track. That is the
enforcement-before-adoption deadlock `.ai/ci-gate-discipline.md` forbids
resolving with a lever, so the severity is scoped by CONTEXT instead.

**The signal is one that already exists.** `reusable-release-dispatch.yml`
invokes the preflight as `just check-fleet-conformance
--emit-member-verdicts member-verdicts.json`, tolerating exit 4 when the
verdict artifact is present, while per-PR CI invokes the check bare and
treats exit 4 as failure. Emitting per-member verdicts therefore ALREADY
means "my findings are consumed by the dispatch-matrix filter", so
`FleetContext.filter_consuming_preflight` is derived from that flag rather
than from a new lever, env var, or exemption.

This mirrors `1e85cd1`'s vantage-classification in SPIRIT only. That
change keys on credential CLASS (the `ghs_` prefix via
`holds_app_class_credential`), which cannot separate these two contexts:
the per-PR CI job and the fan-out preflight both hold the same fleet App
installation token. The discriminator has to be the invocation, not the
credential.

The diagnostic MESSAGE is deliberately identical in both contexts — only
the severity moves — so an operator reading per-PR CI still sees the
persisting gap named, and the warning does not become a silent pass.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Protocol, cast

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    GhResult,
    GhRunner,
    RowFinding,
)

__all__: list[str] = []


_MEMBER = FleetMember(repo="widget", repo_class="impl-plugin")
_TREE_ARGS: tuple[str, ...] = ("api", "repos/acme/widget/git/trees/master?recursive=1")
_LATEST_LIVESPEC_ARGS: tuple[str, ...] = ("api", "repos/acme/livespec/releases/latest")
_OPEN_PRS_ARGS: tuple[str, ...] = ("api", "repos/acme/widget/pulls?state=open&per_page=100")


class PinCurrencyRow(Protocol):
    """One pin-currency row assertion."""

    def __call__(self, *, ctx: FleetContext, member: FleetMember) -> object: ...


def _module() -> object:
    module_path = (
        Path(__file__).resolve().parents[3]
        / "livespec_dev_tooling"
        / "fleet"
        / "_rows_pin_currency.py"
    )
    assert module_path.is_file()
    return importlib.import_module("livespec_dev_tooling.fleet._rows_pin_currency")


def _raw_args(*, path: str) -> tuple[str, ...]:
    return (
        "api",
        f"repos/acme/widget/contents/{path}?ref=master",
        "-H",
        "Accept: application/vnd.github.raw",
    )


def _bump_pr(*, number: int, source: str, tag: str) -> dict[str, object]:
    return {
        "number": number,
        "title": f"chore(deps): bump {source} pin to {tag}",
        "head": {"ref": f"bump-{source}-{tag}"},
    }


def _context(*, filter_consuming_preflight: bool) -> FleetContext:
    """A widget whose compat pin is stale AND already has an open bump PR.

    The fixture pins the PERSISTING conjunction in both contexts; only the
    context flag differs between the two tests, so any severity difference
    is attributable to the scoping and nothing else.
    """
    files = {
        ".livespec.jsonc": json.dumps(
            {"impl-plugin": {"compat": {"pinned": "v1.0.0", "livespec": "v1"}}}
        )
    }
    tree_payload = {
        "tree": [{"path": path, "mode": "100644"} for path in files],
        "truncated": False,
    }
    table = {
        _TREE_ARGS: GhResult(returncode=0, stdout=json.dumps(tree_payload), stderr=""),
        _LATEST_LIVESPEC_ARGS: GhResult(
            returncode=0, stdout=json.dumps({"tag_name": "v1.1.0"}), stderr=""
        ),
        _OPEN_PRS_ARGS: GhResult(
            returncode=0,
            stdout=json.dumps([_bump_pr(number=7, source="livespec", tag="v1.1.0")]),
            stderr="",
        ),
    }
    for path, text in files.items():
        table[_raw_args(path=path)] = GhResult(returncode=0, stdout=text, stderr="")

    def run(*, args: list[str], stdin: str | None = None) -> GhResult:
        del stdin
        return table.get(tuple(args), GhResult(returncode=1, stdout="", stderr="no canned"))

    runner: GhRunner = run
    return FleetContext(
        owner="acme",
        run_gh=runner,
        filter_consuming_preflight=filter_consuming_preflight,
    )


def _row(*, module: object) -> PinCurrencyRow:
    return cast("PinCurrencyRow", module.assert_livespec_compat_pin_currency)


def test_persisting_gap_is_a_warning_in_per_pr_ci_context() -> None:
    """Default context (no per-member verdicts emitted) keeps the gap at warning.

    This is the per-PR CI invocation. The gap must still be NAMED — the
    scoping lowers severity, it does not suppress the diagnostic — so the
    message is asserted to carry the persisting wording and the PR number
    exactly as the preflight context does.
    """
    module = _module()
    ctx = _context(filter_consuming_preflight=False)

    outcome = _row(module=module)(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "warning", (
        f"a persisting gap must NOT red per-PR CI, where a sibling member's "
        f"stall would block unrelated (and repair) PRs in this repo; "
        f"got severity={outcome.severity!r} message={outcome.message!r}"
    )
    assert "persisting" in outcome.message
    assert "#7" in outcome.message


def test_persisting_gap_is_an_error_in_the_filter_consuming_preflight() -> None:
    """The fan-out preflight context still escalates, so the filter excludes the member.

    Exit 4 here is consumed by the `livespec-f73t` per-member filter as a
    loud exclusion rather than a halt, so escalating is safe in this
    context and is what gives the alarm its teeth.
    """
    module = _module()
    ctx = _context(filter_consuming_preflight=True)

    outcome = _row(module=module)(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "error", (
        f"the preflight context must still escalate a persisting gap so the "
        f"dispatch-matrix filter excludes the member; "
        f"got severity={outcome.severity!r} message={outcome.message!r}"
    )
    assert "persisting" in outcome.message
    assert "#7" in outcome.message


def test_both_contexts_emit_the_identical_diagnostic_message() -> None:
    """Only severity is context-scoped; the operator-facing text is one string.

    Guards against the scoping drifting into two divergent message
    formats, which would make a per-PR CI warning read as a different
    (lesser) finding than the preflight error it is.
    """
    module = _module()

    warning_outcome = _row(module=_module())(
        ctx=_context(filter_consuming_preflight=False), member=_MEMBER
    )
    error_outcome = _row(module=module)(
        ctx=_context(filter_consuming_preflight=True), member=_MEMBER
    )

    assert isinstance(warning_outcome, RowFinding)
    assert isinstance(error_outcome, RowFinding)
    assert warning_outcome.message == error_outcome.message

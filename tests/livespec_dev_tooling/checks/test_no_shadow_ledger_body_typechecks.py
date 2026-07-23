"""Outside-in test for `livespec_dev_tooling/checks/no_shadow_ledger_body_typechecks.py`.

The check renders the wheel-safe carrier constant
`livespec_dev_tooling.install_no_shadow_ledger.CANONICAL_NO_SHADOW_LEDGER_BODY`
to a throwaway `.py` and runs pyright in strict mode against it. The pass/fail
verdict is pyright's EXIT CODE (0 = clean → exit 0; non-zero = diagnostics →
exit 4), which is robust to a freshly-bootstrapped pyright printing
platform-detection noise to stdout ahead of its JSON; the JSON is parsed only
best-effort to name the failing lines/rules.

Coverage strategy: two arms run pyright for real — `main()` proves the SHIPPED
canonical body is strict-clean (exit 0), and `_typecheck_body` on a
deliberately-untyped fixture body proves a regression is caught (exit 4). The
pyright-unavailable skip, the noise-tolerant JSON locator (`_locate_pyright_json`),
the detail formatter (`_diagnostic_detail`) with its raw-output fallback, and the
diagnostic summarizers (`_one_based_line` / `_summary_line`) are exercised
in-process with synthetic inputs, so their edge branches are covered without a
second pyright spawn.
"""

from __future__ import annotations

import json

import pytest

from livespec_dev_tooling.checks.no_shadow_ledger_body_typechecks import (
    _configure_logger,
    _diagnostic_detail,
    _locate_pyright_json,
    _one_based_line,
    _summary_line,
    _typecheck_body,
    main,
)

__all__: list[str] = []


# A minimal body carrying a genuine pyright-strict violation (an unannotated
# parameter): pyright MUST exit non-zero, so the check must return 4.
_DIRTY_BODY = "def _needs_annotation(value):\n    return value\n"

# Pyright `--outputjson` payload with a single error diagnostic, optionally
# preceded by the platform-detection noise a fresh runner prints to stdout.
_JSON_WITH_ERROR = json.dumps(
    {
        "version": "1.1.391",
        "generalDiagnostics": [
            {
                "severity": "error",
                "rule": "reportFoo",
                "message": "bad thing\nsecond line",
                "range": {"start": {"line": 3, "character": 0}},
            }
        ],
        "summary": {"errorCount": 1},
    },
    indent=4,
)
_BOOTSTRAP_NOISE = "{'x86': False, 'risc': False, 'lts': False}\n"


# --- real-pyright arms -----------------------------------------------------


def test_passes_on_clean_canonical_body() -> None:
    """(a) the shipped canonical body is pyright-strict clean → exit 0 via main()."""
    assert main() == 0


def test_flags_dirty_body() -> None:
    """(b) a body with a strict violation → pyright exits non-zero → exit 4."""
    log = _configure_logger()

    assert _typecheck_body(body=_DIRTY_BODY, log=log) == 4


# --- pyright-unavailable skip ----------------------------------------------


def test_skips_when_pyright_unavailable(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """(c) pyright not importable → graceful skip (exit 0), no type-check attempted."""
    import livespec_dev_tooling.checks.no_shadow_ledger_body_typechecks as module

    monkeypatch.setattr(module, "_pyright_available", lambda: False)
    log = _configure_logger()

    assert _typecheck_body(body=_DIRTY_BODY, log=log) == 0


# --- JSON locator (_locate_pyright_json) -----------------------------------


def test_locate_parses_clean_json() -> None:
    """A clean pyright JSON payload parses to the object."""
    located = _locate_pyright_json(stdout=_JSON_WITH_ERROR)

    assert located is not None
    assert located.get("version") == "1.1.391"


def test_locate_skips_leading_bootstrap_noise() -> None:
    """Platform-detection noise before the JSON is skipped; the object still parses."""
    located = _locate_pyright_json(stdout=_BOOTSTRAP_NOISE + _JSON_WITH_ERROR)

    assert located is not None
    assert "generalDiagnostics" in located


def test_locate_returns_none_when_no_json() -> None:
    """Output with no parseable JSON object yields None."""
    assert _locate_pyright_json(stdout="not json at all\nsecond line") is None


# --- detail formatter (_diagnostic_detail) ---------------------------------


def test_detail_summarizes_located_diagnostics() -> None:
    """Located diagnostics are rendered as compact summary lines (noise tolerated)."""
    assert _diagnostic_detail(stdout=_BOOTSTRAP_NOISE + _JSON_WITH_ERROR) == [
        "L4 reportFoo: bad thing"
    ]


def test_detail_falls_back_to_raw_when_no_json() -> None:
    """Unparseable output falls back to the raw non-empty lines."""
    assert _diagnostic_detail(stdout="boom\n\nsecond line") == ["boom", "second line"]


def test_detail_falls_back_to_raw_when_no_diagnostics_key() -> None:
    """A JSON object without a `generalDiagnostics` list falls back to raw output."""
    assert _diagnostic_detail(stdout='{"summary": {}}') == ['{"summary": {}}']


def test_detail_falls_back_to_raw_when_no_dict_entries() -> None:
    """A `generalDiagnostics` list with no dict entries yields no summaries → raw output."""
    stdout = '{"generalDiagnostics": ["oops"]}'

    assert _diagnostic_detail(stdout=stdout) == [stdout]


# --- diagnostic summarizers (_one_based_line / _summary_line) --------------


def test_one_based_line_from_zero_based_range() -> None:
    """A 0-based pyright line is reported 1-based."""
    diagnostic: dict[str, object] = {"range": {"start": {"line": 130}}}

    assert _one_based_line(diagnostic=diagnostic) == 131


def test_one_based_line_defaults_to_zero_when_range_absent() -> None:
    """No range → line 0."""
    assert _one_based_line(diagnostic={}) == 0


def test_one_based_line_defaults_to_zero_when_start_malformed() -> None:
    """A non-dict `start` → line 0."""
    assert _one_based_line(diagnostic={"range": {"start": "x"}}) == 0


def test_one_based_line_defaults_to_zero_when_line_not_int() -> None:
    """A non-int `line` → line 0."""
    assert _one_based_line(diagnostic={"range": {"start": {"line": "x"}}}) == 0


def test_summary_line_full_shape() -> None:
    """A well-formed diagnostic renders `L<line> <rule>: <first message line>`."""
    diagnostic: dict[str, object] = {
        "rule": "reportUnusedCallResult",
        "message": "Result of call expression is unused\nsecond line",
        "range": {"start": {"line": 4}},
    }

    assert (
        _summary_line(diagnostic=diagnostic)
        == "L5 reportUnusedCallResult: Result of call expression is unused"
    )


def test_summary_line_defaults_when_rule_and_message_absent() -> None:
    """A rule-less / message-less diagnostic renders the `(no-rule)` placeholder and empty tail."""
    assert _summary_line(diagnostic={}) == "L0 (no-rule): "

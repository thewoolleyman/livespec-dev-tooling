"""Tests for `livespec_dev_tooling/fleet/_cli_parser.py`.

The parser was lifted out of `fleet_conformance.py` verbatim, so what is
worth asserting is that the CLI SURFACE did not move in the process: the
flags callers already pass must still parse, and the defaults must still
be the defaults. A silently renamed flag or a flipped default would be a
behavior change wearing a refactor's clothes.
"""

from __future__ import annotations

from pathlib import Path

from livespec_dev_tooling.fleet._cli_parser import build_parser

__all__: list[str] = []


def test_parser_identity_is_preserved() -> None:
    assert build_parser().prog == "fleet-conformance"


def test_owner_flag_parses() -> None:
    assert build_parser().parse_args(["--owner", "thewoolleyman"]).owner == "thewoolleyman"


def test_empty_argv_keeps_every_default() -> None:
    """Defaults are part of the surface: an extraction must not re-baseline them."""
    assert vars(build_parser().parse_args([])) == {
        "owner": None,
        "emit_member_verdicts": None,
        "member_ci": False,
    }


def test_emit_member_verdicts_parses_as_a_path() -> None:
    parsed = build_parser().parse_args(["--emit-member-verdicts", "/tmp/verdicts.json"])
    assert parsed.emit_member_verdicts == Path("/tmp/verdicts.json")


def test_member_ci_is_a_flag_that_defaults_off() -> None:
    """The lane selector, asserted in BOTH positions — it changes exit semantics."""
    assert build_parser().parse_args([]).member_ci is False
    assert build_parser().parse_args(["--member-ci"]).member_ci is True

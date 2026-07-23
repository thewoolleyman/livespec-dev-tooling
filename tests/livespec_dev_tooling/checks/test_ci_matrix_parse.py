"""Docstring pins for the BOUNDED parser-duplication convention.

`livespec_dev_tooling/checks/_ci_matrix_parse.py` carries the package's
parser-duplication convention as module-docstring prose. The bound is a
maintainer decision on work-item livespec-dev-tooling-6cf, recorded after
the previously unbounded "each check duplicates small self-contained
parsers" convention caused the livespec-dev-tooling-ahg defect: a drifted
parser copy lost a spec rule and reported eight false positives against a
correctly configured fleet. The decision notes require that the bound
"must not remain aspirational" — these pins make the LOAD-BEARING clauses
mechanically checked wording, so a later docstring edit cannot silently
drop the rule while the surrounding prose still reads plausibly.

Pinned clauses (loose substring assertions on distinctive phrases over
whitespace-normalized text, so cosmetic rewrapping or rewording of the
surrounding prose does not false-fail):

- the FORBIDDEN-for-rule-encoding clause — sharing is mandatory for any
  parser encoding a rule that originates in the spec;
- the mechanical marker — a livespec SPECIFICATION citation in a
  parser's docstring/comments defines that parser as rule-encoding;
- the permitted-duplicate naming of `_tool_backed_surfaces.py`'s
  `_parse_ci_matrix_targets`, so nobody consolidates it reflexively.
"""

from __future__ import annotations

from livespec_dev_tooling.checks import _ci_matrix_parse

__all__: list[str] = []


_FORBIDDEN_CLAUSE = (
    "Duplication is FORBIDDEN for any parser that encodes a rule originating in the spec"
)
_SHARED_MODULE_CLAUSE = "MUST live in a shared module"
_CITATION_MARKER_CLAUSE = "cite a livespec SPECIFICATION section"
_RULE_ENCODING_BY_DEFINITION_CLAUSE = "is by definition rule-encoding"
_PERMITTED_DUPLICATE_SYMBOL = "_parse_ci_matrix_targets"
_PERMITTED_DUPLICATE_CLAUSE = "PERMITTED under the bound"


def _normalized_doc() -> str:
    """Return the module docstring with all whitespace runs collapsed to one space."""
    doc = _ci_matrix_parse.__doc__
    assert doc is not None, "_ci_matrix_parse must carry a module docstring"
    return " ".join(doc.split())


def test_forbidden_for_rule_encoding_clause_is_pinned() -> None:
    """The docstring forbids duplicating any parser that encodes a spec rule."""
    doc = _normalized_doc()
    assert _FORBIDDEN_CLAUSE in doc, (
        "the bounded convention's forbidding half is missing: the docstring must "
        f"state {_FORBIDDEN_CLAUSE!r} (work-item livespec-dev-tooling-6cf)"
    )
    assert _SHARED_MODULE_CLAUSE in doc, (
        "the bounded convention must require rule-encoding parsers to live in a "
        f"shared module: {_SHARED_MODULE_CLAUSE!r} is missing"
    )


def test_spec_citation_mechanical_marker_is_pinned() -> None:
    """The docstring defines the spec-citation marker that makes the bound checkable."""
    doc = _normalized_doc()
    assert _CITATION_MARKER_CLAUSE in doc, (
        "the mechanical marker is missing: the docstring must define a parser whose "
        f"docstring/comments {_CITATION_MARKER_CLAUSE!r} as rule-encoding"
    )
    assert (
        _RULE_ENCODING_BY_DEFINITION_CLAUSE in doc
    ), f"the marker must be definitional: {_RULE_ENCODING_BY_DEFINITION_CLAUSE!r} is missing"


def test_tool_backed_surfaces_duplicate_stays_permitted() -> None:
    """The docstring names `_parse_ci_matrix_targets` as a duplicate that STAYS."""
    doc = _normalized_doc()
    assert _PERMITTED_DUPLICATE_SYMBOL in doc, (
        "the permitted-duplicate example is missing: the docstring must name "
        f"{_PERMITTED_DUPLICATE_SYMBOL!r} so nobody consolidates it reflexively"
    )
    assert (
        _PERMITTED_DUPLICATE_CLAUSE in doc
    ), f"the permitted-duplicate example must be marked {_PERMITTED_DUPLICATE_CLAUSE!r}"

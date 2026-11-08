"""Pure CI/source parity evaluation for this repository's gate severity levers."""

from __future__ import annotations

import re

from livespec_dev_tooling.checks._ci_matrix_evaluate import Finding, finding

__all__: list[str] = ["ci_severity_lever_findings"]


_CI_LEVER = re.compile(r"^\s*(LIVESPEC_FAIL_IF_[A-Z0-9_]+)\s*:", re.MULTILINE)
_SOURCE_LEVER = re.compile(r"^\s*export\s+(LIVESPEC_FAIL_IF_[A-Z0-9_]+)=", re.MULTILINE)

_MISSING_FROM_SOURCE = (
    "ci.yml arms a LIVESPEC_FAIL_IF_* severity lever absent from the committed "
    "gate-surface severity-lever source"
)
_MISSING_FROM_CI = (
    "the committed gate-surface severity-lever source names a LIVESPEC_FAIL_IF_* "
    "lever that ci.yml does not arm"
)


def ci_severity_lever_findings(*, ci_yml: str, source: str) -> list[Finding]:
    """Report every lever present on exactly one of the CI and source surfaces."""
    ci_levers = set(_CI_LEVER.findall(ci_yml))
    source_levers = set(_SOURCE_LEVER.findall(source))
    return [
        *(
            finding(
                mode="ci-severity-lever-missing-from-source",
                message=_MISSING_FROM_SOURCE,
                lever=lever,
            )
            for lever in sorted(ci_levers - source_levers)
        ),
        *(
            finding(
                mode="source-severity-lever-missing-from-ci",
                message=_MISSING_FROM_CI,
                lever=lever,
            )
            for lever in sorted(source_levers - ci_levers)
        ),
    ]

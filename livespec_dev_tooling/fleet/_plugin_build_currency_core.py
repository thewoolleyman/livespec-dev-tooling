"""Pure served-versus-expected plugin build currency decisions."""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__: list[str] = [
    "CURRENCY_CURRENT",
    "CURRENCY_STALE",
    "CURRENCY_UNDETERMINABLE",
    "BuildIdentifier",
    "PluginBuildCurrency",
    "build_currency",
    "resolved_build",
    "unresolved_build",
]

CURRENCY_CURRENT = "CURRENT"
CURRENCY_STALE = "STALE"
CURRENCY_UNDETERMINABLE = "UNDETERMINABLE"

_FULL_COMMIT_SHA = re.compile(r"[0-9a-f]{40}")


@dataclass(frozen=True, kw_only=True)
class BuildIdentifier:
    """One resolved full commit SHA, or the reason it could not be resolved."""

    sha: str
    unresolved: str


@dataclass(frozen=True, kw_only=True)
class PluginBuildCurrency:
    """One plugin's served build compared with its locally expected build."""

    plugin: str
    verdict: str
    served: str
    expected: str
    detail: str

    @property
    def line(self) -> str:
        """Render the complete verdict without hiding either comparison side."""
        served = self.served or "<unresolved>"
        expected = self.expected or "<unresolved>"
        detail = f"; {self.detail}" if self.detail else ""
        return f"{self.plugin} {self.verdict}: " f"served={served} expected={expected}{detail}"


def resolved_build(*, sha: str) -> BuildIdentifier:
    """Normalize a build identifier read from a registry or git."""
    return BuildIdentifier(sha=sha.strip().lower(), unresolved="")


def unresolved_build(*, detail: str) -> BuildIdentifier:
    """Represent an unanswered build probe distinctly from a mismatch."""
    return BuildIdentifier(sha="", unresolved=detail)


def build_currency(
    *, plugin: str, served: BuildIdentifier, expected: BuildIdentifier
) -> PluginBuildCurrency:
    """Compare two full SHAs; every absent or malformed side is undeterminable."""
    problems = tuple(
        filter(
            None,
            (
                _identifier_problem(side="served", build=served),
                _identifier_problem(side="expected", build=expected),
            ),
        )
    )
    if problems:
        return PluginBuildCurrency(
            plugin=plugin,
            verdict=CURRENCY_UNDETERMINABLE,
            served=served.sha,
            expected=expected.sha,
            detail="; ".join(problems),
        )
    verdict = CURRENCY_CURRENT if served.sha == expected.sha else CURRENCY_STALE
    return PluginBuildCurrency(
        plugin=plugin,
        verdict=verdict,
        served=served.sha,
        expected=expected.sha,
        detail="",
    )


def _identifier_problem(*, side: str, build: BuildIdentifier) -> str:
    """Explain why one comparison side cannot participate in an exact match."""
    if build.unresolved:
        return f"{side} build unresolved: {build.unresolved}"
    if _FULL_COMMIT_SHA.fullmatch(build.sha) is None:
        return f"{side} build identifier is not a full commit sha"
    return ""

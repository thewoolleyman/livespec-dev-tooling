"""A return annotation that is a type ALIAS to `Result`/`IOResult` is compliant.

`_is_railway_compliant` compared the annotation's TERMINAL NAME against
`{"Result", "IOResult"}`, which a type alias defeats. MEASURED on this repo:
`fleet/_snapshot.py` declares `SnapshotResult = IOResult[TreeSnapshot,
SnapshotUnavailable]` and annotates `memoized_snapshot -> SnapshotResult`, so
the check convicted a function that is ALREADY on the railway.

⛔ THIS IS FIDELITY, NOT SOFTENING, AND IT IS THE MIRROR OF THE `_`-FILE SKIP.
That skip is non-conformance with ratified v178 in the RELAXING direction —
clause 0 disqualifies a `_`-prefixed NAME, never a FILE. This is
non-conformance in the TIGHTENING direction: the ratified rule requires the
return to BE `Result`/`IOResult`, and an alias to `IOResult` IS `IOResult`. PR
#748 is the precedent — wiring the spec's own stated exemptions in was fidelity
rather than softening.

A separate file from `test_public_api_result_typed.py` because that one is a
multi-assertion suite and this is the Red-recorded half of a Red→Green pair.
"""

from __future__ import annotations

from pathlib import Path

from livespec_dev_tooling.checks.public_api_result_typed import _find_offenders

__all__: list[str] = []


_REL = Path("pkg/a.py")
_PUBLIC = frozenset({"aliased", "plain", "shadowed"})


def _offender_names(*, source: str) -> list[str]:
    return [
        name
        for _lineno, name in _find_offenders(
            source=source,
            rel_path=_REL,
            commands_trees=(),
            public_names=_PUBLIC,
        )
    ]


def test_a_return_annotated_with_an_alias_to_ioresult_is_compliant() -> None:
    """The measured false positive: `SnapshotResult = IOResult[...]`.

    `plain` in the same fixture is the discriminator — it returns an ordinary
    value and must STAY an offender, so a check that simply stopped reading
    annotations would not pass this.
    """
    source = (
        "from returns.io import IOResult\n"
        "\n"
        "SnapshotResult = IOResult[str, OSError]\n"
        "\n"
        "def aliased(*, at: str) -> SnapshotResult:\n"
        "    return IOResult.from_value(at)\n"
        "\n"
        "def plain(*, at: str) -> str:\n"
        "    return at\n"
    )
    assert _offender_names(source=source) == ["plain"]


def test_an_alias_to_result_is_compliant_and_a_subscripted_alias_still_resolves() -> None:
    """Both railway heads alias, and the alias may itself carry parameters."""
    source = (
        "from returns.result import Result\n"
        "\n"
        "Parsed = Result[int, str]\n"
        "\n"
        "def aliased(*, raw: str) -> Parsed:\n"
        "    return Result.from_value(len(raw))\n"
    )
    assert _offender_names(source=source) == []


def test_an_alias_to_something_that_is_not_the_railway_is_still_an_offender() -> None:
    """The bound the fix must not exceed.

    Resolving aliases must resolve them to what they ACTUALLY name. An alias to
    a plain container is not a railway type, and a fix that treated every
    module-level assignment as compliant would silently exempt the whole repo.
    """
    source = (
        "Outcome = dict[str, int]\n"
        "\n"
        "def aliased(*, raw: str) -> Outcome:\n"
        "    return {raw: 1}\n"
    )
    assert _offender_names(source=source) == ["aliased"]


def test_a_name_shadowed_by_a_local_alias_does_not_make_an_offender_compliant() -> None:
    """An alias defined INSIDE a function is not a module-level type alias.

    Without this the fix could read any assignment anywhere in the file.
    """
    source = (
        "from returns.io import IOResult\n"
        "\n"
        "def shadowed(*, at: str) -> Hidden:\n"
        "    Hidden = IOResult[str, OSError]\n"
        "    return at\n"
    )
    assert _offender_names(source=source) == ["shadowed"]

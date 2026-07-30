"""The canonical-slug surface is on the railway, and an EMPTY WALK IS A FAILURE.

`livespec-dev-tooling-vzwa`. `canonical_check_slugs` and `world_gate_check_slugs`
reach the filesystem through `_discover_slugs` → `pkgutil.iter_modules`, so ratified
livespec v179 member 1 clause (c) reaches them — TRANSITIVELY, via clause (d)'s
fixpoint, which is why a hand reading of their own clean bodies called both exempt
and the mechanism disagreed.

**THE LOAD-BEARING ASSERTION IN THIS FILE IS THE FAILURE ONE, not the successes.**
`pkgutil.iter_modules` on a MISSING directory yields no entries rather than raising,
so the pre-conversion surface returned an EMPTY TUPLE and every consumer read that as
"this repo has no canonical checks" — which PASSES. Typing the function `IOResult`
while still returning `IOSuccess(())` for an empty walk would MOVE that sentinel
rather than remove it. So the empty walk must come back on the FAILURE track, and
that is what this file pins.

**BOTH FUNCTIONS ARE ASSERTED, because clause (d) couples them.**
`world_gate_check_slugs` calls `canonical_check_slugs`, so it is two hops from the
walk and cannot be total while the inner one is not. Converting only one would leave
the other still reported — the check would measure 2 → 2 and read as a failed
conversion.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from returns.io import IOFailure, IOSuccess

if TYPE_CHECKING:
    from types import ModuleType

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CANONICAL_CHECKS = _REPO_ROOT / "livespec_dev_tooling" / "canonical_checks.py"


def _import_canonical_checks() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "canonical_checks_railway_under_test", str(_CANONICAL_CHECKS)
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_canonical_check_slugs_returns_an_io_success_over_the_real_package() -> None:
    """The happy path is on the railway, and it unwraps TO ITS VALUE.

    Asserting merely that the call succeeded is what the `dx8l` bug also satisfied,
    so this reads the slugs back out through `unsafe_perform_io` — the only correct
    extraction, since `IOResult.unwrap()` returns `IO[T]` and `tuple(IO(...))`
    SUCCEEDS while yielding a tuple holding the container.
    """
    from returns.unsafe import unsafe_perform_io

    module = _import_canonical_checks()

    result = module.canonical_check_slugs()

    assert isinstance(
        result, IOSuccess
    ), f"canonical_check_slugs() must return IOResult per v179; got {type(result)}"
    slugs = unsafe_perform_io(result.unwrap())
    assert isinstance(slugs, tuple) and slugs, f"expected a non-empty tuple; got {slugs!r}"
    assert all(slug.startswith("check-") for slug in slugs), f"unexpected slug shape: {slugs!r}"


def test_world_gate_check_slugs_is_also_on_the_railway() -> None:
    """Clause (d) couples the pair, so both convert or neither does."""
    from returns.unsafe import unsafe_perform_io

    module = _import_canonical_checks()

    result = module.world_gate_check_slugs()

    assert isinstance(result, IOSuccess), (
        f"world_gate_check_slugs() is two hops from the walk and must be IOResult too; "
        f"got {type(result)}"
    )
    assert unsafe_perform_io(result.unwrap()), "the world-gate registry must be non-empty"


def test_an_unreadable_checks_package_is_a_failure_not_an_empty_success(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """⛔ THE LOAD-BEARING TEST. An empty walk MUST come back on the failure track.

    `pkgutil.iter_modules` on a missing directory yields NO entries and does not
    raise, so before this conversion the function returned `()` and every consumer
    read it as "no canonical checks" — a PASS. Returning `IOSuccess(())` here would
    relocate that sentinel instead of removing it, which is exactly what
    `livespec-dev-tooling-vzwa` warned against.
    """
    module = _import_canonical_checks()
    missing = tmp_path / "definitely-not-a-package"
    monkeypatch.setattr(module, "_CHECKS_PACKAGE_DIR", missing)

    result = module.canonical_check_slugs()

    assert isinstance(result, IOFailure), (
        f"an unreadable checks package must be a FAILURE, never an empty success; "
        f"got {type(result)}"
    )


def test_the_failure_names_the_path_and_says_why_it_is_not_merely_empty(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The failure payload has to be actionable, not just non-success.

    A caller that receives an unnamed failure cannot tell a broken install from a
    misconfiguration, and this is the one place that distinction is available.
    """
    from returns.unsafe import unsafe_perform_io

    module = _import_canonical_checks()
    missing = tmp_path / "definitely-not-a-package"
    monkeypatch.setattr(module, "_CHECKS_PACKAGE_DIR", missing)

    result = module.canonical_check_slugs()
    assert isinstance(result, IOFailure), f"expected IOFailure; got {type(result)}"

    unreadable = unsafe_perform_io(result.failure())
    assert (
        unreadable.package_path == missing
    ), f"the failure must name the path it walked; got {unreadable.package_path}"
    assert (
        "empty walk is a broken install" in unreadable.reason
    ), f"the reason must say why an empty walk is not an answer; got {unreadable.reason!r}"


def test_world_gate_forwards_the_failure_rather_than_re_wrapping_it(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The outer function adds no failure mode of its own, so it forwards.

    Two error types for one condition would make a caller distinguish two things
    that are one thing.
    """
    from returns.unsafe import unsafe_perform_io

    module = _import_canonical_checks()
    missing = tmp_path / "definitely-not-a-package"
    monkeypatch.setattr(module, "_CHECKS_PACKAGE_DIR", missing)

    result = module.world_gate_check_slugs()

    assert isinstance(result, IOFailure), f"expected IOFailure; got {type(result)}"
    assert (
        unsafe_perform_io(result.failure()).package_path == missing
    ), "world_gate_check_slugs must forward the inner failure unchanged"

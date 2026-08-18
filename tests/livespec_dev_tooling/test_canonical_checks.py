"""Outside-in test for `livespec_dev_tooling/canonical_checks.py` — canonical-check enumeration.

This module is the single source of truth enumerating which
`checks/*.py` modules are universally wired across the livespec
fleet. It is consumed by:

- `aggregate_completeness` (Phase 1.3 of epic li-univck) — set-
  membership + ordering comparison against consumer justfiles.
- `livespec/templates/impl-plugin/justfile.jinja` (Phase 2.2) —
  stamping the aggregate at copier-copy time.
- doctor's cross-repo invariant (Phase 2.3) — fleet-wide drift
  detection.

Discovery is dynamic (over the real `livespec_dev_tooling.checks`
package directory) so adding a new check file automatically extends
the canonical set on next invocation. The tests here exercise the
discovery primitive (`_discover_slugs`) against synthetic fixture
directories so the suite does not bind to the live `checks/`
directory contents (which would flake every time a new check
landed).

Three invariants pinned here:

1. **Alphabetical ordering.** The returned tuple is always
   alphabetically sorted, regardless of filesystem iteration order.
2. **Underscore-prefix exclusion.** Helper modules (e.g.,
   `_red_green_replay_modes`) are filtered out so they never
   appear in the canonical set.
3. **`__init__.py` exclusion.** Package marker files are not
   checks and are filtered out.

Plus the snake_case → kebab-case slug mapping (file `foo_bar.py`
→ slug `check-foo-bar`) and the thin-transport `--json` surface
shape (`{"slugs": [...]}` on stdout, exit 0).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from returns.io import IOFailure, IOSuccess
from returns.unsafe import unsafe_perform_io

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CANONICAL_CHECKS = _REPO_ROOT / "livespec_dev_tooling" / "canonical_checks.py"


def _write_check_module(*, package_dir: Path, name: str) -> None:
    """Create a stub check module at `<package_dir>/<name>.py`.

    Stub content is irrelevant to discovery — only the filename
    matters. Body is a no-op so the file parses cleanly.
    """
    (package_dir / f"{name}.py").write_text(
        "from __future__ import annotations\n" "\n" "__all__: list[str] = []\n",
        encoding="utf-8",
    )


def _make_fixture_package(*, tmp_path: Path, module_names: list[str]) -> Path:
    """Create a synthetic `checks/` package with the given module filenames.

    Returns the package directory (with `__init__.py` present), ready
    to pass to `_discover_slugs` via the live module's API.
    """
    pkg = tmp_path / "checks"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(
        '"""Synthetic test fixture package."""\n\n__all__: list[str] = []\n',
        encoding="utf-8",
    )
    for module_name in module_names:
        _write_check_module(package_dir=pkg, name=module_name)
    return pkg


def _import_canonical_checks() -> object:
    """Import `livespec_dev_tooling.canonical_checks` fresh for direct API use."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "canonical_checks_for_test",
        str(_CANONICAL_CHECKS),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # REGISTERING IN `sys.modules` IS REQUIRED, not tidiness. Since
    # `livespec-dev-tooling-vzwa` the module defines a `@dataclass`
    # (`ChecksPackageUnreadable`), and under `from __future__ import annotations`
    # `dataclasses` resolves field annotations by looking up
    # `sys.modules[cls.__module__]`. For a module loaded via
    # `spec_from_file_location` and never registered, that lookup yields None and
    # the decorator dies with `'NoneType' object has no attribute '__dict__'` —
    # BEFORE any test body runs, so the failure names the import, not the cause.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_discover_slugs_returns_alphabetical_order(*, tmp_path: Path) -> None:
    """`_discover_slugs` returns slugs in alphabetical order regardless of input.

    Fixture: three check modules created in a non-alphabetical
    order (`zebra`, `apple`, `mango`). Discovery must return
    them sorted: `check-apple`, `check-mango`, `check-zebra`.
    """
    pkg = _make_fixture_package(
        tmp_path=tmp_path,
        module_names=["zebra", "apple", "mango"],
    )
    module = _import_canonical_checks()

    slugs = module._discover_slugs(package_path=pkg)  # noqa: SLF001  — internal helper under test  # pyright: ignore[reportPrivateUsage]

    assert slugs == (
        "check-apple",
        "check-mango",
        "check-zebra",
    ), f"discovery must return alphabetically-sorted slugs; got {slugs}"


def test_discover_slugs_excludes_underscore_prefixed_modules(*, tmp_path: Path) -> None:
    """`_discover_slugs` filters out modules whose name starts with `_`.

    Fixture: a `_red_green_replay_modes.py` helper alongside a
    real `keyword_only_args.py`. Discovery must skip the
    underscore-prefixed helper and return only the real check.
    """
    pkg = _make_fixture_package(
        tmp_path=tmp_path,
        module_names=["_red_green_replay_modes", "keyword_only_args"],
    )
    module = _import_canonical_checks()

    slugs = module._discover_slugs(package_path=pkg)  # noqa: SLF001  — internal helper under test  # pyright: ignore[reportPrivateUsage]

    assert slugs == (
        "check-keyword-only-args",
    ), f"discovery must exclude underscore-prefixed helpers; got {slugs}"


def test_discover_slugs_excludes_init_py(*, tmp_path: Path) -> None:
    """`_discover_slugs` filters out `__init__.py` from the slug set.

    Fixture: `__init__.py` is always present in a real package
    directory. The fixture-helper already creates one. Discovery
    must not emit a `check-` slug derived from `__init__`.
    """
    pkg = _make_fixture_package(
        tmp_path=tmp_path,
        module_names=["foo"],
    )
    module = _import_canonical_checks()

    slugs = module._discover_slugs(package_path=pkg)  # noqa: SLF001  — internal helper under test  # pyright: ignore[reportPrivateUsage]

    assert (
        "check-init" not in slugs
    ), f"discovery must not emit a check- slug for __init__; got {slugs}"
    assert (
        "check---init--" not in slugs
    ), f"discovery must not emit any __init__-derived slug; got {slugs}"
    assert slugs == ("check-foo",), f"discovery must return only the real check module; got {slugs}"


def test_discover_slugs_maps_snake_case_to_kebab_case(*, tmp_path: Path) -> None:
    """`_discover_slugs` maps `foo_bar_baz` → `check-foo-bar-baz`.

    Fixture: `keyword_only_args.py` (multi-underscore name).
    Discovery must replace `_` with `-` and prepend `check-`.
    """
    pkg = _make_fixture_package(
        tmp_path=tmp_path,
        module_names=["keyword_only_args"],
    )
    module = _import_canonical_checks()

    slugs = module._discover_slugs(package_path=pkg)  # noqa: SLF001  — internal helper under test  # pyright: ignore[reportPrivateUsage]

    assert slugs == (
        "check-keyword-only-args",
    ), f"discovery must map snake_case → kebab-case; got {slugs}"


def test_discover_slugs_handles_empty_package(*, tmp_path: Path) -> None:
    """`_discover_slugs` returns the empty tuple for a package with no checks.

    Fixture: package directory with only `__init__.py`, no other
    modules. Discovery must return `()`.
    """
    pkg = _make_fixture_package(
        tmp_path=tmp_path,
        module_names=[],
    )
    module = _import_canonical_checks()

    slugs = module._discover_slugs(package_path=pkg)  # noqa: SLF001  — internal helper under test  # pyright: ignore[reportPrivateUsage]

    assert slugs == (), f"discovery must return empty tuple for empty package; got {slugs}"


def test_canonical_check_slugs_returns_tuple_of_strings() -> None:
    """`canonical_check_slugs()` yields a tuple of slugs over the real checks package.

    The surface is `IOResult` since `livespec-dev-tooling-vzwa`, so this unwraps; the
    RAILWAY shape and the empty-walk failure are pinned in
    `test_canonical_checks_railway.py` rather than duplicated here.

    Integration-style check: invokes the public API with no
    arguments. The result must be a tuple of strings, each
    prefixed with `check-`, sorted alphabetically. We don't bind
    to a specific count or specific slug names (that would flake
    every time a new check landed); we bind to the invariants the
    surface promises.
    """
    module = _import_canonical_checks()

    slugs = unsafe_perform_io(module.canonical_check_slugs().unwrap())

    assert isinstance(
        slugs, tuple
    ), f"canonical_check_slugs() must yield a tuple of slugs; got {type(slugs)}"
    assert all(
        isinstance(s, str) for s in slugs
    ), f"every slug must be a string; got {[type(s) for s in slugs]}"
    assert all(
        s.startswith("check-") for s in slugs
    ), f"every slug must start with `check-`; got {slugs}"
    assert list(slugs) == sorted(slugs), f"slugs must be alphabetically sorted; got {slugs}"
    assert (
        "check-keyword-only-args" in slugs
    ), f"real check `keyword_only_args` must appear in the canonical set; got {slugs}"
    assert (
        "check-primary-checkout-commit-refuse-hook-installed" in slugs
    ), f"real check `primary_checkout_commit_refuse_hook_installed` must appear; got {slugs}"


def test_canonical_check_slugs_excludes_helper_module() -> None:
    """The live `canonical_check_slugs()` excludes `_red_green_replay_modes`.

    The repo carries `livespec_dev_tooling/checks/_red_green_replay_modes.py`
    as a helper. The canonical set must not include it under any
    naming.
    """
    module = _import_canonical_checks()

    slugs = unsafe_perform_io(module.canonical_check_slugs().unwrap())

    assert (
        "check--red-green-replay-modes" not in slugs
    ), f"underscore-prefixed helper must not appear in canonical set; got {slugs}"
    assert (
        "check-red-green-replay-modes" not in slugs
    ), f"underscore-prefixed helper (stripped form) must not appear; got {slugs}"


def test_json_thin_transport_emits_slugs_array() -> None:
    """`python -m livespec_dev_tooling.canonical_checks --json` emits `{"slugs": [...]}`.

    Thin-transport contract per epic li-univck Phase 1.2:
    stdout is a single JSON object with a `slugs` key whose
    value is an alphabetically-sorted list of strings. Exit 0.
    """
    # S603: argv is a fixed list (sys.executable + package -m
    # invocation); no untrusted shell input.
    result = subprocess.run(
        [sys.executable, "-m", "livespec_dev_tooling.canonical_checks", "--json"],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        f"--json thin-transport must exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    payload = json.loads(result.stdout)
    assert isinstance(
        payload, dict
    ), f"--json output must be a JSON object; got {type(payload).__name__}"
    assert (
        "slugs" in payload
    ), f"--json output must have a `slugs` key; got keys {list(payload.keys())}"
    slugs = payload["slugs"]
    assert isinstance(slugs, list), f"`slugs` must be a list; got {type(slugs).__name__}"
    assert all(
        isinstance(s, str) for s in slugs
    ), f"every slug must be a string; got {[type(s).__name__ for s in slugs]}"
    assert all(
        s.startswith("check-") for s in slugs
    ), f"every slug must start with `check-`; got {slugs}"
    assert slugs == sorted(slugs), f"slugs must be alphabetically sorted; got {slugs}"


def test_canonical_checks_module_importable_without_running_main() -> None:
    """The canonical_checks module imports cleanly without invoking main().

    Closes the `if __name__ == "__main__":` else-arm (module
    imported via importlib, not run as a script) required for
    per-file 100% line + branch coverage.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "canonical_checks_importable_test",
        str(_CANONICAL_CHECKS),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Same `sys.modules` requirement as `_import_canonical_checks` — see the comment
    # there. The module's `@dataclass` cannot resolve its annotations otherwise.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    assert callable(
        module.canonical_check_slugs
    ), "canonical_check_slugs must be importable without invocation"
    assert callable(module.main), "main must be importable without invocation"


def test_baseline_check_slugs_returns_the_seeded_slug() -> None:
    """`baseline_check_slugs()` returns exactly the curated baseline profile.

    Seeded with one Verifier per Conformance-Pattern concern that carries a
    shared baseline check: Cross-harness plugin-resolution (concern #2,
    `check-plugin-resolution`) and Worktree-discipline (concern #1,
    `check-primary-checkout-commit-refuse-hook-installed`). Bound to the exact
    (alphabetically-sorted) tuple — not just membership — because the baseline
    profile is a deliberately small curated registry whose contents are a
    product decision, not a filesystem derivation.
    """
    module = _import_canonical_checks()

    slugs = module.baseline_check_slugs()

    assert slugs == (
        "check-plugin-resolution",
        "check-primary-checkout-commit-refuse-hook-installed",
    ), f"baseline profile must be the curated two-slug set; got {slugs}"


def test_baseline_check_slugs_are_sorted_and_subset_of_canonical() -> None:
    """Every baseline slug is alphabetically sorted AND a real canonical check slug."""
    module = _import_canonical_checks()

    baseline = module.baseline_check_slugs()
    canonical = unsafe_perform_io(module.canonical_check_slugs().unwrap())

    assert list(baseline) == sorted(baseline), f"baseline slugs must be sorted; got {baseline}"
    for slug in baseline:
        assert slug in canonical, f"baseline slug {slug} missing from canonical set"


def test_validate_baseline_subset_passes_for_canonical_subset() -> None:
    """`_validate_baseline_subset` is a no-op when every baseline slug is canonical."""
    module = _import_canonical_checks()

    result = module._validate_baseline_subset(  # noqa: SLF001  — internal invariant guard under test
        baseline=("check-foo", "check-bar"),
        canonical=("check-foo", "check-bar", "check-baz"),
    )

    assert result is None


def test_validate_baseline_subset_raises_for_non_canonical_slug() -> None:
    """`_validate_baseline_subset` raises AssertionError on a non-canonical baseline slug."""
    module = _import_canonical_checks()

    with pytest.raises(AssertionError):
        module._validate_baseline_subset(  # noqa: SLF001  — internal invariant guard under test
            baseline=("check-not-a-real-check",),
            canonical=("check-foo",),
        )


def test_world_gate_check_slugs_returns_the_curated_set() -> None:
    """`world_gate_check_slugs()` returns exactly the curated world-gate set.

    The world-gate checks verify master/world state (not the PR change) —
    `check-branch-protection-alignment` (branch-protection config),
    `check-master-ci-green` (master CI status), and
    `check-plan-epic-parity` (beads ledger-state parity, read under the
    maintainer's credentials) — and are excluded from
    `check-ci-matrix-completeness`'s CI-mirror requirement (assertion (a)).
    Bound to the exact (alphabetically-sorted) tuple — not just membership —
    because the world-gate set is a deliberately small curated registry whose
    contents are a product decision, not a filesystem derivation.
    """
    module = _import_canonical_checks()

    slugs = unsafe_perform_io(module.world_gate_check_slugs().unwrap())

    assert slugs == (
        "check-branch-protection-alignment",
        "check-master-ci-green",
        "check-plan-epic-parity",
    ), f"world-gate set must be the curated set; got {slugs}"


def test_world_gate_check_slugs_are_sorted_and_subset_of_canonical() -> None:
    """Every world-gate slug is alphabetically sorted AND a real canonical check slug."""
    module = _import_canonical_checks()

    world_gates = unsafe_perform_io(module.world_gate_check_slugs().unwrap())
    canonical = unsafe_perform_io(module.canonical_check_slugs().unwrap())

    assert list(world_gates) == sorted(
        world_gates
    ), f"world-gate slugs must be sorted; got {world_gates}"
    for slug in world_gates:
        assert slug in canonical, f"world-gate slug {slug} missing from canonical set"


def test_validate_world_gate_subset_passes_for_canonical_subset() -> None:
    """`_validate_world_gate_subset` is a no-op when every world-gate slug is canonical."""
    module = _import_canonical_checks()

    result = module._validate_world_gate_subset(  # noqa: SLF001  — internal invariant guard under test
        world_gates=("check-foo", "check-bar"),
        canonical=("check-foo", "check-bar", "check-baz"),
    )

    assert result is None


def test_validate_world_gate_subset_raises_for_non_canonical_slug() -> None:
    """`_validate_world_gate_subset` raises AssertionError on a non-canonical world-gate slug."""
    module = _import_canonical_checks()

    with pytest.raises(AssertionError):
        module._validate_world_gate_subset(  # noqa: SLF001  — internal invariant guard under test
            world_gates=("check-not-a-real-check",),
            canonical=("check-foo",),
        )


def test_canonical_check_renames_returns_the_curated_rename_map() -> None:
    """`canonical_check_renames()` returns exactly the curated old->new rename pairs.

    Seeded with the three renames from `042a7854` ("retire 'plan thread'
    vocabulary in check module names and slugs", epic livespec-dev-tooling-jaut4y):
    the OLD `plan_thread_*` modules were deleted from `checks/`, so a consumer
    whose justfile/CI still wires the old slug breaks with `ModuleNotFoundError`
    the moment its pin bumps past that commit (livespec-dev-tooling-3gy1). The
    reconcile modules consult this map to rewrite a stranded old slug to its
    replacement instead of leaving it to explode.
    """
    module = _import_canonical_checks()

    outcome = module.canonical_check_renames()
    assert isinstance(
        outcome, IOSuccess
    ), f"canonical_check_renames() must succeed; got {type(outcome).__name__}"
    renames = unsafe_perform_io(outcome.unwrap())

    assert renames == (
        ("check-plan-thread-anchor-declared", "check-plan-anchor-declared"),
        ("check-plan-thread-epic-parity", "check-plan-epic-parity"),
        ("check-plan-thread-no-tombstone", "check-plan-no-tombstone"),
    ), f"rename map must be the curated three-pair set; got {renames}"


def test_canonical_check_renames_new_slugs_are_canonical() -> None:
    """Every rename's `new` slug is a real canonical check slug (the old slug is not)."""
    module = _import_canonical_checks()

    outcome = module.canonical_check_renames()
    assert isinstance(
        outcome, IOSuccess
    ), f"canonical_check_renames() must succeed; got {type(outcome).__name__}"
    renames = unsafe_perform_io(outcome.unwrap())
    canonical = unsafe_perform_io(module.canonical_check_slugs().unwrap())

    for old, new in renames:
        assert new in canonical, f"rename target {new} missing from canonical set"
        assert old not in canonical, f"rename source {old} must NOT still be canonical"


def test_validate_check_renames_passes_for_canonical_targets() -> None:
    """`_validate_check_renames` is a no-op when every rename target is canonical."""
    module = _import_canonical_checks()

    result = module._validate_check_renames(  # noqa: SLF001  — internal invariant guard under test
        renames=(("check-old", "check-new"),),
        canonical=("check-new", "check-other"),
    )

    assert result is None


def test_validate_check_renames_raises_for_non_canonical_target() -> None:
    """`_validate_check_renames` raises AssertionError when a rename target isn't canonical."""
    module = _import_canonical_checks()

    with pytest.raises(AssertionError):
        module._validate_check_renames(  # noqa: SLF001  — internal invariant guard under test
            renames=(("check-old", "check-not-a-real-check"),),
            canonical=("check-foo",),
        )


def test_canonical_check_renames_forwards_the_failure_rather_than_re_wrapping_it(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The outer function adds no failure mode of its own, so it forwards.

    `canonical_check_renames` is two hops from the walk via `canonical_check_slugs`
    and adds no failure mode of its own, so it forwards.

    Two error types for one condition would make a caller distinguish two things
    that are one thing.
    """
    module = _import_canonical_checks()
    missing = tmp_path / "definitely-not-a-package"
    monkeypatch.setattr(module, "_CHECKS_PACKAGE_DIR", missing)

    result = module.canonical_check_renames()

    assert isinstance(result, IOFailure), f"expected IOFailure; got {type(result)}"
    assert (
        unsafe_perform_io(result.failure()).package_path == missing
    ), "canonical_check_renames must forward the inner failure unchanged"

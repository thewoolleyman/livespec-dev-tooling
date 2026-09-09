"""Consumer-tier: the two surfaces this library publishes, and their exit contract.

Covers two `SPECIFICATION/spec.md` headings.

§"Project intent" states the library MUST publish a Python package
consumable via `uv` git source AND a set of GitHub composite Actions plus
reusable workflows, and that consumers MUST use both surfaces IN CONCERT —
the Python package for local `just check` invocations, the composite
Actions and reusable workflows for CI. "In concert" is consumer-observable
as ONE entrypoint set behind both paths: the CI surface's `run-check`
composite Action and every local `just check-<slug>` recipe name the same
`livespec_dev_tooling.checks.<slug>` module namespace, neither path names a
module the package does not ship, and every shipped slug the CI matrix may
thread resolves in that namespace. A consumer whose CI runs the Actions
while its developers run `just check` would otherwise be running two
divergent suites and never learn it.

§"Architecture" states each `livespec_dev_tooling/checks/<slug>.py` module
is invocable as `python -m livespec_dev_tooling.checks.<slug>` and MUST
exit `0` on pass or non-zero on fail, with structured stderr describing the
failure. That is exercised against a synthetic mini fixture: one shipped
check is driven over a clean tree and over a tree carrying a
deliberately-injected violation, and BOTH legs are asserted — an exit code
alone says nothing about the failing leg's diagnostic, which is the half a
consumer's CI log actually shows.

The check is driven IN-PROCESS (`monkeypatch.chdir` + `capsys` + `rc =
main()`) rather than through a `sys.executable` child: a consumer reaches
the same `main()` whichever way it names the module, and the in-process
call starts no `COVERAGE_PROCESS_START`-instrumented child to race the
parallel dispatcher's coverage writes.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import re
from pathlib import Path
from typing import cast

import pytest
from returns.io import IOSuccess
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.canonical_checks import canonical_check_slugs

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PYPROJECT = _REPO_ROOT / "pyproject.toml"
_JUSTFILE = _REPO_ROOT / "justfile"
_RUN_CHECK_ACTION = _REPO_ROOT / ".github" / "actions" / "run-check" / "action.yml"
_CHECK_MATRIX_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "reusable-check-matrix.yml"

# The module namespace both consumption paths name. The CI surface spells the
# slug as an Action input template; the local surface spells it literally in
# each `just check-<slug>` recipe.
_CI_MODULE_TEMPLATE = "livespec_dev_tooling.checks.${{ inputs.check-name }}"
_LOCAL_MODULE_PATTERN = re.compile(r"livespec_dev_tooling\.checks\.([a-z0-9_]+)")

# The distribution name a consumer's `[tool.uv.sources]` git+tag pin resolves
# to, read from the consumer-facing pin source itself. Matched as text rather
# than parsed: stdlib `tomllib` lands in 3.11 and this repo's floor is 3.10.
_PYPROJECT_NAME_LINE = re.compile(r'^name = "livespec-dev-tooling"$', re.MULTILINE)

# The shipped check driven end-to-end below. It reads its whole world from the
# working directory (a spec tree plus the coverage registry) and needs no
# role-key configuration, so a two-file fixture is a complete input.
_DRIVEN_CHECK = "livespec_dev_tooling.checks.heading_coverage"
_FIXTURE_HEADING = "## Project intent"


def _canonical_module_names() -> set[str]:
    """The package's canonical check modules, derived from the shipped slugs."""
    resolved = canonical_check_slugs()
    assert isinstance(
        resolved, IOSuccess
    ), f"the shipped checks package must be readable; got {resolved}"
    slugs = unsafe_perform_io(resolved.unwrap())
    return {slug.removeprefix("check-").replace("-", "_") for slug in slugs}


def _write_fixture_tree(*, root: Path, registry: str) -> None:
    """A minimal consumer tree: one spec heading plus the coverage registry."""
    spec_dir = root / "SPECIFICATION"
    spec_dir.mkdir(parents=True, exist_ok=True)
    _ = spec_dir.joinpath("spec.md").write_text(
        f"# Fixture spec\n\n{_FIXTURE_HEADING}\n\nProse.\n", encoding="utf-8"
    )
    tests_dir = root / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    _ = tests_dir.joinpath("heading-coverage.json").write_text(registry, encoding="utf-8")


def _structured_event(*, line: str) -> dict[str, object]:
    """One stderr line as a structured event; a non-object line fails the assertion."""
    parsed: object = json.loads(line)
    assert isinstance(parsed, dict), f"each stderr line must be a JSON object; got {line!r}"
    return cast("dict[str, object]", parsed)


def _structured_stderr_events(*, stderr: str) -> list[dict[str, object]]:
    """Every non-blank stderr line parsed as a structured event."""
    return [_structured_event(line=line) for line in stderr.splitlines() if line.strip()]


def test_both_published_surfaces_name_one_check_entrypoint_set() -> None:
    """The package surface and the Actions/workflows surface resolve to one entrypoint set.

    The `spec.md` §"Project intent" obligation: both surfaces are published,
    and a consumer uses them in concert rather than running two suites.
    """
    pyproject = _PYPROJECT.read_text(encoding="utf-8")
    assert (
        _PYPROJECT_NAME_LINE.search(pyproject) is not None
    ), "the distribution a consumer pins via `[tool.uv.sources]` git+tag must keep its name"
    assert "[build-system]" in pyproject, (
        "a `uv` git-source consumer builds the package from the tagged checkout, "
        "so the build backend must be declared"
    )

    modules = _canonical_module_names()
    assert modules, "the Python package surface must ship at least one check module"
    resolution = {
        module: importlib.util.find_spec(f"livespec_dev_tooling.checks.{module}")
        for module in sorted(modules)
    }
    unimportable = sorted(name for name, found in resolution.items() if found is None)
    assert not unimportable, (
        f"every slug the CI matrix may thread must resolve in the package namespace; "
        f"unimportable={unimportable}"
    )

    action = _RUN_CHECK_ACTION.read_text(encoding="utf-8")
    assert _CI_MODULE_TEMPLATE in action, (
        f"the run-check composite Action must invoke the package namespace "
        f"`{_CI_MODULE_TEMPLATE}`; a divergent namespace splits the two surfaces"
    )
    workflow = _CHECK_MATRIX_WORKFLOW.read_text(encoding="utf-8")
    assert (
        ".github/actions/run-check" in workflow
    ), "the reusable check-matrix must run each matrix entry through the run-check Action"
    assert (
        "check-name: ${{ matrix.check }}" in workflow
    ), "the reusable check-matrix must thread each matrix slug into the Action's check-name"

    local_modules = set(_LOCAL_MODULE_PATTERN.findall(_JUSTFILE.read_text(encoding="utf-8")))
    assert local_modules, "the local `just check-<slug>` surface must invoke the package"
    assert local_modules <= modules, (
        f"a `just` recipe names a check module the package does not ship, so the local "
        f"surface has drifted from the shipped one; extra={sorted(local_modules - modules)}"
    )


def test_a_shipped_check_exits_zero_on_pass_and_nonzero_with_structured_stderr_on_fail(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The `python -m` entrypoint's exit-code and structured-stderr contract, both legs.

    The `spec.md` §"Architecture" obligation for every module of the Python
    package surface: exit `0` on pass, non-zero on fail with structured
    stderr describing the failure.
    """
    module = importlib.import_module(_DRIVEN_CHECK)

    clean = tmp_path / "clean"
    _write_fixture_tree(
        root=clean,
        registry=json.dumps(
            [
                {
                    "spec_root": "SPECIFICATION",
                    "spec_file": "spec.md",
                    "heading": _FIXTURE_HEADING,
                    "test": "tests.fixture.test_intent.test_intent",
                }
            ]
        ),
    )
    monkeypatch.chdir(clean)
    clean_rc = module.main()
    clean_captured = capsys.readouterr()

    assert clean_rc == 0, f"a clean fixture must exit 0; stderr={clean_captured.err}"

    violating = tmp_path / "violating"
    _write_fixture_tree(root=violating, registry="[]")
    monkeypatch.chdir(violating)
    violating_rc = module.main()
    violating_captured = capsys.readouterr()

    assert violating_rc != 0, "an injected violation must exit non-zero"
    events = _structured_stderr_events(stderr=violating_captured.err)
    assert any(
        event.get("level") == "error" and event.get("heading") == _FIXTURE_HEADING
        for event in events
    ), f"the failing exit must carry a structured diagnostic naming the violation; events={events}"

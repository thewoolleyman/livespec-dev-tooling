"""Outside-in test for `livespec_dev_tooling/checks/canonical_recipe_fidelity.py`.

The anti-fork guard: for every canonical check slug, the consumer's
`justfile` MUST declare a `check-<slug>:` recipe whose body invokes the
pinned shared module `python -m livespec_dev_tooling.checks.<module>`.
This closes the gap `aggregate_completeness` (targets-array membership
only) and `tool_backed_check_completeness` (four tool slugs) leave
open: neither inspects the recipe BODY, so a consumer can satisfy both
while repointing a shared check at a local script / bash fork (the
"B1" incident).

Failure modes covered:

- Recipe present but repointed to a `bash …/fork.sh` copy → exit 1 with
  a `recipe_not_pinned_to_shared_module` finding.
- Recipe absent entirely → exit 1 with a `canonical_recipe_missing`
  finding.
- Justfile missing at cwd → exit 4 with a `justfile_not_found` finding.

Acceptance behaviors:

- Every canonical recipe invokes the shared module → exit 0.
- Recipe headers carrying `*args` parameters still match.
- The prefix-collision guard: a lookup for `check-foo` does NOT match a
  `check-foo-bar:` header.

The check is exercised IN-PROCESS via `main()` (`monkeypatch.chdir` +
`monkeypatch.setattr(sys, "argv", ...)` + `capsys`) — the repo's
preferred pattern over spawning a Python subprocess, which keeps the
module coverage-measurable in-process. Tests inject a synthetic
canonical set via `--canonical-from` so they stay hermetic from the
live `checks/` package (the check module's own slug
`check-canonical-recipe-fidelity` is in the live set, which would
otherwise couple tests to sibling landings).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "canonical_recipe_fidelity.py"


def _load_check_module() -> ModuleType:
    """Import the check module fresh from its file path."""
    spec = importlib.util.spec_from_file_location(
        "canonical_recipe_fidelity_under_test",
        str(_CHECK),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Register before exec so module-scope `@dataclass(kw_only=True)`
    # can resolve `KW_ONLY` via `sys.modules[cls.__module__]`.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_MODULE = _load_check_module()


class _CheckRun(NamedTuple):
    returncode: int
    stdout: str
    stderr: str


def _run_check(
    *,
    cwd: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    extra_argv: list[str] | None = None,
) -> _CheckRun:
    monkeypatch.chdir(cwd)
    argv = ["canonical_recipe_fidelity", *(extra_argv or [])]
    monkeypatch.setattr(sys, "argv", argv)
    rc = _MODULE.main()
    captured = capsys.readouterr()
    return _CheckRun(returncode=rc, stdout=captured.out, stderr=captured.err)


def _write_justfile(*, cwd: Path, body: str) -> Path:
    path = cwd / "justfile"
    _ = path.write_text(body, encoding="utf-8")
    return path


def _write_canonical_json(*, cwd: Path, slugs: list[object]) -> Path:
    path = cwd / "canonical.json"
    _ = path.write_text(json.dumps({"slugs": slugs}), encoding="utf-8")
    return path


def _good_recipe(*, slug: str) -> str:
    """Render a `check-<slug>:` recipe whose body invokes the shared module."""
    module = slug[len("check-") :].replace("-", "_")
    return f"{slug}:\n    uv run python -m livespec_dev_tooling.checks.{module}\n"


def _justfile_with_recipes(*, recipes: list[str]) -> str:
    """Render a minimal justfile carrying a `default:` recipe plus `recipes`."""
    return "default:\n    @just --list\n\n" + "\n".join(recipes)


def _parse_findings(*, stderr: str) -> list[dict[str, object]]:
    """Parse structlog JSON-per-line findings from the check's stderr."""
    return [json.loads(line) for line in stderr.splitlines() if line.strip().startswith("{")]


def test_all_canonical_recipes_invoke_shared_module_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every canonical `check-<slug>:` recipe invokes the shared module → exit 0."""
    slugs = ["check-alpha", "check-beta", "check-wrapper-shape"]
    _ = _write_canonical_json(cwd=tmp_path, slugs=list(slugs))
    recipes = [_good_recipe(slug=s) for s in slugs]
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_recipes(recipes=recipes))
    result = _run_check(
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        extra_argv=["--canonical-from", "canonical.json"],
    )
    assert (
        result.returncode == 0
    ), f"expected exit 0 when all recipes invoke the shared module; stderr={result.stderr!r}"
    assert result.stderr == ""


def test_repointed_bash_fork_recipe_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A canonical recipe repointed to a `bash …/fork.sh` copy → exit 1 + finding.

    This is the "B1" incident shape: `check-wrapper-shape:` repointed
    from `python -m livespec_dev_tooling.checks.wrapper_shape` to a
    strictly-weaker local bash fork.
    """
    slugs = ["check-alpha", "check-wrapper-shape"]
    _ = _write_canonical_json(cwd=tmp_path, slugs=list(slugs))
    forked = "check-wrapper-shape:\n    bash dev-tooling/checks/wrapper-shape-compat.sh\n"
    recipes = [_good_recipe(slug="check-alpha"), forked]
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_recipes(recipes=recipes))
    result = _run_check(
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        extra_argv=["--canonical-from", "canonical.json"],
    )
    assert (
        result.returncode == 1
    ), f"expected exit 1 on a repointed recipe; got {result.returncode}, stderr={result.stderr!r}"
    findings = _parse_findings(stderr=result.stderr)
    repointed = [
        f
        for f in findings
        if f.get("status") == "fail"
        and f.get("failure_mode") == "recipe_not_pinned_to_shared_module"
    ]
    assert len(repointed) == 1, f"expected one repointed finding; got {repointed!r}"
    assert repointed[0].get("slug") == "check-wrapper-shape"
    assert (
        repointed[0].get("expected_invocation")
        == "python -m livespec_dev_tooling.checks.wrapper_shape"
    )


def test_missing_canonical_recipe_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A canonical slug with no `check-<slug>:` recipe → exit 1 + distinct finding."""
    slugs = ["check-alpha", "check-beta"]
    _ = _write_canonical_json(cwd=tmp_path, slugs=list(slugs))
    # `check-beta` recipe is absent entirely.
    recipes = [_good_recipe(slug="check-alpha")]
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_recipes(recipes=recipes))
    result = _run_check(
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        extra_argv=["--canonical-from", "canonical.json"],
    )
    assert (
        result.returncode == 1
    ), f"expected exit 1 on a missing recipe; got {result.returncode}, stderr={result.stderr!r}"
    findings = _parse_findings(stderr=result.stderr)
    missing = [
        f
        for f in findings
        if f.get("status") == "fail" and f.get("failure_mode") == "canonical_recipe_missing"
    ]
    assert len(missing) == 1, f"expected one missing-recipe finding; got {missing!r}"
    assert missing[0].get("slug") == "check-beta"


def test_recipe_with_args_parameter_matches(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `check-<slug> *args:` recipe header (parameters) still matches and passes.

    Exercises the `[^\\n]*?:` header tail that consumes `*args` before the
    colon — the real form of `check-red-green-replay *args:` /
    `check-check-coverage-incremental *args:`.
    """
    slugs = ["check-replay"]
    _ = _write_canonical_json(cwd=tmp_path, slugs=list(slugs))
    recipe = (
        "check-replay *args:\n" "    uv run python -m livespec_dev_tooling.checks.replay {{args}}\n"
    )
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_recipes(recipes=[recipe]))
    result = _run_check(
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        extra_argv=["--canonical-from", "canonical.json"],
    )
    assert (
        result.returncode == 0
    ), f"expected exit 0 for a parameterized recipe header; stderr={result.stderr!r}"


def test_prefix_collision_guard_does_not_match_longer_slug(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A lookup for `check-foo` does NOT match a `check-foo-bar:` header → missing.

    The header regex's `(?=[ \\t:])` lookahead requires the character
    after the slug to be whitespace or the colon (never `-`), so a
    shorter canonical slug never latches onto a longer recipe name.
    """
    slugs = ["check-foo"]
    _ = _write_canonical_json(cwd=tmp_path, slugs=list(slugs))
    # Only a `check-foo-bar:` recipe exists — `check-foo` is genuinely absent.
    recipe = _good_recipe(slug="check-foo-bar")
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_recipes(recipes=[recipe]))
    result = _run_check(
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        extra_argv=["--canonical-from", "canonical.json"],
    )
    assert (
        result.returncode == 1
    ), f"expected exit 1 (check-foo absent); got {result.returncode}, stderr={result.stderr!r}"
    findings = _parse_findings(stderr=result.stderr)
    missing = [f for f in findings if f.get("failure_mode") == "canonical_recipe_missing"]
    assert (
        len(missing) == 1 and missing[0].get("slug") == "check-foo"
    ), f"expected check-foo reported missing (not latched onto check-foo-bar); got {missing!r}"


def test_recipe_body_stops_at_next_recipe_header(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `check-<slug>:` recipe followed by another recipe → body scan stops at the header.

    Exercises the `break` branch in `_extract_recipe_body` where a
    non-indented `name:` line terminates the body. The following recipe
    carries the shared-module string; if the body did NOT stop, the
    check would spuriously pass a repointed recipe — so this asserts the
    repoint is still caught.
    """
    slugs = ["check-alpha"]
    _ = _write_canonical_json(cwd=tmp_path, slugs=list(slugs))
    body = (
        "default:\n"
        "    @just --list\n"
        "\n"
        "check-alpha:\n"
        "    bash dev-tooling/checks/alpha-fork.sh\n"
        "\n"
        "other-recipe:\n"
        "    uv run python -m livespec_dev_tooling.checks.alpha\n"
    )
    _ = _write_justfile(cwd=tmp_path, body=body)
    result = _run_check(
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        extra_argv=["--canonical-from", "canonical.json"],
    )
    assert result.returncode == 1, (
        f"expected exit 1: check-alpha is a fork and the module string belongs to a "
        f"following recipe; got {result.returncode}, stderr={result.stderr!r}"
    )
    findings = _parse_findings(stderr=result.stderr)
    repointed = [
        f for f in findings if f.get("failure_mode") == "recipe_not_pinned_to_shared_module"
    ]
    assert len(repointed) == 1, f"expected one repointed finding; got {repointed!r}"


def test_missing_justfile_fails_gracefully(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No justfile at cwd → exit 4 with a structured `justfile_not_found` finding."""
    _ = _write_canonical_json(cwd=tmp_path, slugs=["check-alpha"])
    result = _run_check(
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        extra_argv=["--canonical-from", "canonical.json"],
    )
    assert (
        result.returncode == 4
    ), f"expected exit 4 when justfile missing; got {result.returncode}, stderr={result.stderr!r}"
    findings = _parse_findings(stderr=result.stderr)
    absence = [f for f in findings if f.get("failure_mode") == "justfile_not_found"]
    assert len(absence) == 1, f"expected one justfile_not_found finding; got {absence!r}"


def test_default_canonical_source_is_live_package(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without `--canonical-from`, the check loads the live canonical set.

    A justfile with no canonical recipes at all, run under the live
    canonical set (non-empty because this check module exists), must
    fail — and `check-canonical-recipe-fidelity` (this module's own
    slug) must appear among the missing-recipe findings.
    """
    _ = _write_justfile(cwd=tmp_path, body="default:\n    @just --list\n")
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert (
        result.returncode == 1
    ), f"expected exit 1 under live canonical set with no recipes; stderr={result.stderr!r}"
    findings = _parse_findings(stderr=result.stderr)
    missing_slugs = {
        f.get("slug") for f in findings if f.get("failure_mode") == "canonical_recipe_missing"
    }
    assert "check-canonical-recipe-fidelity" in missing_slugs, (
        f"expected this check's own slug among missing-recipe findings under the live "
        f"canonical set; got {missing_slugs!r}"
    )


def test_malformed_canonical_slugs_not_a_list_treated_as_empty(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--canonical-from` whose `slugs` is not a list → empty canonical set → exit 0.

    With an empty canonical set there are no recipes to verify, so any
    justfile trivially passes. Exercises the `slug_field` not-a-list
    fallback in `_load_canonical`.
    """
    bad = tmp_path / "canonical.json"
    _ = bad.write_text(json.dumps({"slugs": "not-a-list"}), encoding="utf-8")
    _ = _write_justfile(cwd=tmp_path, body="default:\n    @just --list\n")
    result = _run_check(
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        extra_argv=["--canonical-from", "canonical.json"],
    )
    assert (
        result.returncode == 0
    ), f"expected exit 0 with an empty canonical set; got {result.returncode}, stderr={result.stderr!r}"


def test_canonical_json_top_level_not_a_dict_treated_as_empty(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--canonical-from` whose top-level JSON is a list (not an object) → empty set → exit 0.

    Exercises the `isinstance(parsed, dict)` false branch in
    `_load_canonical` (parsed is not a dict → override is None).
    """
    bad = tmp_path / "canonical.json"
    _ = bad.write_text(json.dumps(["check-alpha"]), encoding="utf-8")
    _ = _write_justfile(cwd=tmp_path, body="default:\n    @just --list\n")
    result = _run_check(
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        extra_argv=["--canonical-from", "canonical.json"],
    )
    assert (
        result.returncode == 0
    ), f"expected exit 0 when top-level JSON is not an object; stderr={result.stderr!r}"


def test_non_string_slug_elements_filtered(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Non-string elements in the `slugs` list are filtered by the isinstance guard.

    `slugs: ["check-alpha", 123]` → only `check-alpha` is treated as a
    canonical slug; a good `check-alpha` recipe passes. Exercises both
    arms of the `isinstance(s, str)` comprehension filter in
    `_load_canonical`.
    """
    _ = _write_canonical_json(cwd=tmp_path, slugs=["check-alpha", 123])
    recipes = [_good_recipe(slug="check-alpha")]
    _ = _write_justfile(cwd=tmp_path, body=_justfile_with_recipes(recipes=recipes))
    result = _run_check(
        cwd=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        extra_argv=["--canonical-from", "canonical.json"],
    )
    assert (
        result.returncode == 0
    ), f"expected exit 0 with the non-string slug filtered out; stderr={result.stderr!r}"


def test_help_flag_exits_zero(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--help` exits 0 with usage text on stdout (argparse raises SystemExit(0))."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["canonical_recipe_fidelity", "--help"])
    with pytest.raises(SystemExit) as excinfo:
        _ = _MODULE.main()
    assert excinfo.value.code == 0
    combined = capsys.readouterr().out.lower()
    assert "canonical-recipe-fidelity" in combined or "usage" in combined

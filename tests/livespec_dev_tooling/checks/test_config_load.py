"""Rendering tests for the shared `load_config_or_report` supervisor helper.

`SPECIFICATION/contracts.md` section "Configuration loader" makes
`ConfigParseError` an IO-layer exception that each check's `main()`
supervisor catches and renders as a structured diagnostic. Measured on
master `dd98bbb0`, exactly ONE of the 33 `load_config` call sites under
`livespec_dev_tooling/checks/` did that — `required_role_keys_declared` —
and the other 32 let the error escape as an uncaught traceback.

That is not merely an unpolished failure mode. A raw traceback reaches
stderr through the interpreter rather than through structlog, so a check
whose whole job is enforcing this package's structlog-only output
discipline broke that discipline itself the moment a consumer's
`pyproject.toml` was malformed — the one moment its diagnostic matters.

These tests pin the RENDERING rather than the catch. Each drives a real
`main()` against a real malformed `pyproject.toml`, so the loader raises
for real and nothing is monkeypatched onto it, and then asserts the whole
supervisor contract: a NON-ZERO return AND one structured event carrying
`check_id`, `status="fail"` and a non-empty `error`. A test that asserted
only "no exception escaped" would pass against a silent `except: pass`,
which is the opposite of what the contract asks for.

The adopted modules are chosen to span the call SHAPES actually present:

- `claude_md_coverage` and `hook_trees_not_io_exempt` load the config
  DIRECTLY in `main()`;
- `check_mutation` loads it one frame DOWN, inside
  `_pure_trees_gate_exit_code`, a helper `main()` calls — so the error
  crosses a frame before anything can render it, and a `main()`-local
  `try` would have been the wrong generalization.

`required_role_keys_declared` is pinned too, deliberately UNMIGRATED. It
is the precedent the helper generalizes, and this pin is what makes
"generalizes" checkable rather than asserted: the migrated surfaces must
emit the same event with the same fields it already emits.

`_config_load` is imported through `importlib` INSIDE the test bodies
rather than at module top so that the Red leg of this change fails on a
genuine assertion — `is_file()` against a module that does not exist yet —
instead of dying at collection with a `ModuleNotFoundError`, which would
prove only unimportability.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

from livespec_dev_tooling.checks import (
    check_mutation,
    claude_md_coverage,
    hook_trees_not_io_exempt,
    required_role_keys_declared,
)

_VENDOR_DIR = Path(claude_md_coverage.__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_HELPER_PATH = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "_config_load.py"
_HELPER_MODULE = "livespec_dev_tooling.checks._config_load"
_HELPER_MISSING = (
    "the shared config-load supervisor helper must live beside the other check "
    f"helpers at {_HELPER_PATH}"
)
# The one wording `required_role_keys_declared` already emits. Generalizing
# that module rather than inventing a second diagnostic shape is the whole
# point, so the string is pinned here rather than read off the new module.
_EVENT = "consumer config parse failed"
# `not [toml` is the same unparseable payload `test_config.py` and
# `test_required_role_keys_declared_edges.py` use, so every one of these
# tests exercises the REAL loader raising a REAL `ConfigParseError`.
_MALFORMED_PYPROJECT = "not [toml"
_RUN_MUTATION_ENV_VAR = "LIVESPEC_RUN_MUTATION"


def _records(*, captured: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in captured.splitlines() if line.strip().startswith("{")]


def _rendered_the_diagnostic(*, captured: str, check_id: str) -> bool:
    """True iff stderr carries one structured parse-failure event for `check_id`."""
    return any(
        record.get("event") == _EVENT
        and record.get("check_id") == check_id
        and record.get("status") == "fail"
        and bool(record.get("error"))
        for record in _records(captured=captured)
    )


def _write_malformed_config(*, repo_root: Path) -> None:
    _ = (repo_root / "pyproject.toml").write_text(_MALFORMED_PYPROJECT, encoding="utf-8")


def _supervisor_logger(*, name: str) -> structlog.stdlib.BoundLogger:
    """Bind a JSON-to-stderr logger shaped exactly like a check supervisor's."""
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger(name)


def test_shared_loader_lives_beside_the_other_check_helpers() -> None:
    """The single definition exists and is exported under the working name."""
    assert _HELPER_PATH.is_file(), _HELPER_MISSING

    module = importlib.import_module(_HELPER_MODULE)

    assert "load_config_or_report" in module.__all__


def test_shared_loader_returns_the_config_when_the_consumer_block_parses(
    *, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The happy path is a pass-through: the helper adds no behavior to a good load."""
    assert _HELPER_PATH.is_file(), _HELPER_MISSING
    module = importlib.import_module(_HELPER_MODULE)
    _ = (tmp_path / "pyproject.toml").write_text(
        '[tool.livespec_dev_tooling]\nsource_trees = ["src"]\n', encoding="utf-8"
    )

    config = module.load_config_or_report(
        repo_root=tmp_path,
        log=_supervisor_logger(name="probe"),
        check_id="probe",
    )

    _ = capsys.readouterr()
    assert config is not None
    assert config.source_trees == (Path("src"),)


def test_shared_loader_renders_the_parse_failure_and_returns_none(
    *, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A malformed block yields the structured event and `None` — never a raise."""
    assert _HELPER_PATH.is_file(), _HELPER_MISSING
    module = importlib.import_module(_HELPER_MODULE)
    _write_malformed_config(repo_root=tmp_path)

    config = module.load_config_or_report(
        repo_root=tmp_path,
        log=_supervisor_logger(name="probe"),
        check_id="probe",
    )

    assert config is None, "the helper must never propagate `ConfigParseError`"
    assert _rendered_the_diagnostic(captured=capsys.readouterr().err, check_id="probe")


def test_claude_md_coverage_main_renders_the_parse_failure(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Shape 1 — `main()` loads the config directly."""
    _write_malformed_config(repo_root=tmp_path)
    monkeypatch.chdir(tmp_path)

    rc = claude_md_coverage.main()

    assert rc != 0, "a malformed consumer config must still exit non-zero"
    assert _rendered_the_diagnostic(captured=capsys.readouterr().err, check_id="claude_md_coverage")


def test_hook_trees_not_io_exempt_main_renders_the_parse_failure(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Shape 1 again, in a check whose `main()` loads before anything else."""
    _write_malformed_config(repo_root=tmp_path)
    monkeypatch.chdir(tmp_path)

    rc = hook_trees_not_io_exempt.main()

    assert rc != 0, "a malformed consumer config must still exit non-zero"
    assert _rendered_the_diagnostic(
        captured=capsys.readouterr().err, check_id="hook_trees_not_io_exempt"
    )


def test_check_mutation_main_renders_the_parse_failure_from_one_frame_down(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Shape 2 — the load happens inside `_pure_trees_gate_exit_code`, not in `main()`.

    The RUN lever is set because the gate sits behind it; without it `main()`
    logs "skipped" and exits 0 long before any config is read, and the test
    would pass against an unfixed tree for the wrong reason.
    """
    _write_malformed_config(repo_root=tmp_path)
    monkeypatch.setenv(_RUN_MUTATION_ENV_VAR, "true")
    monkeypatch.chdir(tmp_path)

    rc = check_mutation.main()

    assert rc != 0, "a malformed consumer config must still exit non-zero"
    assert _rendered_the_diagnostic(captured=capsys.readouterr().err, check_id="check_mutation")


def test_required_role_keys_declared_still_renders_the_parse_failure(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The unmigrated precedent is unchanged — same event, same fields, same exit.

    This one passes before AND after the change on purpose. It is the control
    that makes the generalization checkable: if the shared helper had invented
    a second diagnostic shape, the migrated surfaces above would disagree with
    this one and the divergence would be visible in a single test file.
    """
    _ = (tmp_path / "justfile").write_text(
        "check:\n    targets=(\n        check-no-inheritance\n    )\n", encoding="utf-8"
    )
    _write_malformed_config(repo_root=tmp_path)
    monkeypatch.chdir(tmp_path)

    rc = required_role_keys_declared.main()

    assert rc == 1
    assert _rendered_the_diagnostic(
        captured=capsys.readouterr().err, check_id="required_role_keys_declared"
    )

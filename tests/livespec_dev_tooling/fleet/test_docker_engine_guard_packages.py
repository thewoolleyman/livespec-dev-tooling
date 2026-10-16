"""Tests for the Docker engine install guard's package step (child 3b).

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Package fence". Governing design:
`docs/docker-engine-guard-design.md`, Mechanism 5 as amended by R6, F6 and
G7, plus implementation rider point 4.

Every assertion here runs against RECORDED command output. The step reaches
the world through one injectable runner, so `apt-get`, `apt-cache`, `dpkg`
and `dpkg-deb` are never executed: the fake runner answers the output
measured from a real host and records the `Command` each step emitted, and
the assertions are on THAT argv. One real subprocess runs in this file —
the one that proves the default runner is wired to `subprocess` at all.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__: list[str] = []

_RUNNER_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_package_runner"
_RUNNER_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_package_runner.py")
_AUDIT_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_package_audit.py")
_PACKAGES_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_packages"

# The versions measured on the gmktec host on 2026-10-15, and the archive
# file names `apt-get download` writes for them.
_ENGINE = ("docker.io", "29.1.3-0ubuntu4.1")
_SHIM = ("containerd", "2.2.2-0ubuntu1.1")


def _deb_name(*, package: str, version: str) -> str:
    """The archive file name `apt-get download` writes for one allowlist row."""
    return f"{package}_{version}_amd64.deb"


@dataclass(kw_only=True)
class _RecordedRunner:
    """The one injectable runner, answering nothing and recording every call."""

    result: Any
    calls: list[Any] = field(default_factory=list)

    def __call__(self, *, command: Any) -> Any:
        self.calls.append(command)
        return self.result(returncode=0, stdout="")


def _payload(*, cache: Path) -> dict[str, Any]:
    """The committed package inputs a controller uploads for one run."""
    return {
        "cache": str(cache),
        "allow": [
            {
                "package": package,
                "version": version,
                "deb": _deb_name(package=package, version=version),
            }
            for package, version in (_ENGINE, _SHIM)
        ],
    }


def _declare(*, root: Path, payload: dict[str, Any]) -> Path:
    """Lay out one run's directory with `payload` as its package inputs.

    The downloaded archives are placed in the cache the payload names,
    because the step's own download goes through the fake runner and so
    writes nothing: the files standing in for its result are these.
    """
    cache = Path(str(payload["cache"]))
    cache.mkdir(parents=True, exist_ok=True)
    for package, version in (_ENGINE, _SHIM):
        (cache / _deb_name(package=package, version=version)).write_bytes(b"deb bytes")
    inputs = root / "runs" / "run-a" / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    (inputs / "packages.json").write_text(json.dumps(payload), encoding="utf-8")
    return inputs


def _calls_named(*, runner: _RecordedRunner, argv: tuple[str, ...]) -> list[Any]:
    """Every recorded command whose argv begins with `argv`."""
    return [call for call in runner.calls if tuple(call.argv[: len(argv)]) == argv]


def test_the_package_step_installs_exactly_the_audited_debs_under_the_frontend_lock(
    tmp_path: Path,
) -> None:
    """Specification "Package fence": `dpkg -i` on exactly the audited files.

    Two halves, and both are the fence rather than a convenience. The argv
    is the audited `.deb` SET and nothing else, so the transaction that
    runs is byte-for-byte the one the audit cleared with no resolver
    decision left to apt. And `DPKG_FRONTEND_LOCKED=1` is what tells dpkg
    that its caller already holds the frontend lock (design R6) — without
    it dpkg takes the lock itself and the role's lock-holding helper, which
    has held it since the audit, deadlocks against its own install.
    """
    assert _RUNNER_PATH.is_file()
    assert _AUDIT_PATH.is_file()
    runner_module = importlib.import_module(_RUNNER_MODULE)
    packages = importlib.import_module(_PACKAGES_MODULE)
    inputs = _declare(root=tmp_path, payload=_payload(cache=tmp_path / "cache"))
    runner = _RecordedRunner(result=runner_module.CommandOutput)

    outcome = packages.run_package_step(inputs=inputs, runner=runner)

    assert outcome.refusal is None
    installed = _calls_named(runner=runner, argv=("dpkg", "-i"))
    assert len(installed) == 1
    assert tuple(installed[0].argv) == (
        "dpkg",
        "-i",
        str(tmp_path / "cache" / _deb_name(package=_ENGINE[0], version=_ENGINE[1])),
        str(tmp_path / "cache" / _deb_name(package=_SHIM[0], version=_SHIM[1])),
    )
    assert installed[0].env == {"DPKG_FRONTEND_LOCKED": "1"}
    assert installed[0].timeout_seconds == runner_module.INSTALL_TIMEOUT_SECONDS


def test_the_package_step_refuses_when_the_runs_committed_inputs_are_unreadable(
    tmp_path: Path,
) -> None:
    """A run whose package inputs cannot be read installs nothing at all.

    The refusal is RETURNED rather than raised, which is the Result
    discipline this repository requires carried in the stdlib-only shape
    the guard modules use — they are copied onto the guarded host and run
    against its bare interpreter, where `returns` is not importable.
    """
    assert _RUNNER_PATH.is_file()
    runner_module = importlib.import_module(_RUNNER_MODULE)
    packages = importlib.import_module(_PACKAGES_MODULE)
    inputs = tmp_path / "runs" / "run-a" / "inputs"
    inputs.mkdir(parents=True)
    runner = _RecordedRunner(result=runner_module.CommandOutput)

    outcome = packages.run_package_step(inputs=inputs, runner=runner)

    assert outcome.refusal is not None
    assert "packages.json" in outcome.refusal
    assert runner.calls == []


def test_the_package_step_refuses_committed_inputs_that_declare_no_allowlist(
    tmp_path: Path,
) -> None:
    """Inputs that parse but carry no allowlist are a refusal, not an empty install.

    An absent allowlist read as "install nothing" would make a malformed
    upload indistinguishable from a successful transaction — the step would
    report a clean install having audited nothing.
    """
    assert _RUNNER_PATH.is_file()
    runner_module = importlib.import_module(_RUNNER_MODULE)
    packages = importlib.import_module(_PACKAGES_MODULE)
    payload = _payload(cache=tmp_path / "cache")
    del payload["allow"]
    inputs = _declare(root=tmp_path, payload=payload)
    runner = _RecordedRunner(result=runner_module.CommandOutput)

    outcome = packages.run_package_step(inputs=inputs, runner=runner)

    assert outcome.refusal is not None
    assert "allowlist" in outcome.refusal
    assert runner.calls == []


def test_the_default_runner_spawns_the_argv_and_answers_its_output() -> None:
    """The real runner is the one place the guard's package step spawns anything.

    Asserted against a harmless `/bin/echo` rather than against a mock,
    because the thing worth proving is that the seam is wired to
    `subprocess` with the timeout it was given — every other test in this
    file deliberately proves the opposite, that nothing else spawns.
    """
    assert _RUNNER_PATH.is_file()
    runner_module = importlib.import_module(_RUNNER_MODULE)

    answer = runner_module.default_runner(
        command=runner_module.TimedCommand(
            argv=("/bin/echo", "recorded"),
            timeout_seconds=runner_module.COMMAND_TIMEOUT_SECONDS,
        )
    )

    assert answer.returncode == 0
    assert answer.stdout == "recorded\n"


def test_the_default_runner_adds_its_environment_rather_than_replacing_it() -> None:
    """`env` carries ADDITIONS, so the one variable the fence sets rides along.

    `dpkg -i` needs `DPKG_FRONTEND_LOCKED=1` AND the dpkg environment the
    guard did not build (PATH above all). A runner that passed `env`
    straight through to `subprocess` would hand dpkg an environment of
    exactly one variable.
    """
    assert _RUNNER_PATH.is_file()
    runner_module = importlib.import_module(_RUNNER_MODULE)

    answer = runner_module.default_runner(
        command=runner_module.TimedCommand(
            argv=("/usr/bin/env",),
            timeout_seconds=runner_module.COMMAND_TIMEOUT_SECONDS,
            env={"DPKG_FRONTEND_LOCKED": "1"},
        )
    )

    assert "DPKG_FRONTEND_LOCKED=1" in answer.stdout.splitlines()
    assert any(line.startswith("PATH=") for line in answer.stdout.splitlines())

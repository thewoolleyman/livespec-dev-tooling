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

_RUNNER_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_runner"
_RUNNER_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_runner.py")
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
    """The one injectable runner, answering RECORDED output and recording each call.

    `outputs` pairs an argv prefix with the output measured for it on a
    real host. A prefix carrying more than one output answers them in
    order and then repeats the last, which is how the SAME `dpkg-query`
    the fence runs on both sides of the install answers the host before
    the engine landed and then the host after it.
    """

    result: Any
    outputs: list[tuple[tuple[str, ...], list[str]]] = field(default_factory=list)
    calls: list[Any] = field(default_factory=list)

    def __call__(self, *, command: Any) -> Any:
        self.calls.append(command)
        for prefix, queued in self.outputs:
            if tuple(command.argv[: len(prefix)]) == prefix:
                return self.result(
                    returncode=0,
                    stdout=queued.pop(0) if len(queued) > 1 else queued[0],
                )
        return self.result(returncode=0, stdout="")


# `dpkg-query`'s recorded output in the format the fence asks for: the host
# before the engine lands, and the same host after it. The third line is
# measured output and not padding — `dpkg-query -W` lists a package dpkg
# merely KNOWS OF, from some dependency, with an EMPTY version field and
# the status `not-installed`. Admitted as a package at some version it
# would be a phantom in both the difference and the drift comparison.
_QUERY_BEFORE = """adduser 3.137ubuntu1 installed
libc6 2.39-0ubuntu8.4 installed
docker-compose-v2  not-installed
"""
_QUERY_AFTER = """adduser 3.137ubuntu1 installed
libc6 2.39-0ubuntu8.4 installed
docker-compose-v2  not-installed
containerd 2.2.2-0ubuntu1.1 installed
docker.io 29.1.3-0ubuntu4.1 installed
"""


# `apt-get -s install`'s recorded output for the audited set on a host that
# has never carried the engine: the two `Inst` lines carry a version in
# parentheses and NO bracketed version before it, which is what an install
# of a package not currently held looks like.
_SIMULATION_CLEAN = """NOTE: This is only a simulation!
      apt-get needs root privileges for real execution.
Reading package lists...
Building dependency tree...
The following NEW packages will be installed:
  containerd docker.io
0 upgraded, 2 newly installed, 0 to remove and 0 not upgraded.
Inst containerd (2.2.2-0ubuntu1.1 Ubuntu:24.04/noble-updates [amd64])
Inst docker.io (29.1.3-0ubuntu4.1 Ubuntu:24.04/noble-updates [amd64])
Conf containerd (2.2.2-0ubuntu1.1 Ubuntu:24.04/noble-updates [amd64])
Conf docker.io (29.1.3-0ubuntu4.1 Ubuntu:24.04/noble-updates [amd64])
"""


def _fenced_outputs() -> list[tuple[tuple[str, ...], list[str]]]:
    """The output a clean fenced transaction measures, command by command."""
    return [
        (("apt-get", "-s"), [_SIMULATION_CLEAN]),
        (("dpkg-query",), [_QUERY_BEFORE, _QUERY_AFTER]),
    ]


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
    runner = _RecordedRunner(result=runner_module.CommandOutput, outputs=_fenced_outputs())

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


def test_the_package_step_refuses_a_simulated_transaction_the_allowlist_does_not_cover(
    tmp_path: Path,
) -> None:
    """Specification "Package fence": the three shapes a simulation may not have.

    The simulation is run with `--no-install-recommends --no-remove` and
    the exact pinned specs, so the only transaction apt is asked about is
    the committed one — and then the answer is read line by line anyway,
    because `--no-remove` makes a removal an apt ERROR rather than a
    silent `Remv`, and a resolver that satisfies the pins by UPGRADING
    something already installed has broken nothing apt would complain
    about. Each of the three refuses before anything is mutated.
    """
    assert _RUNNER_PATH.is_file()
    runner_module = importlib.import_module(_RUNNER_MODULE)
    packages = importlib.import_module(_PACKAGES_MODULE)
    inputs = _declare(root=tmp_path, payload=_payload(cache=tmp_path / "cache"))
    clean = _RecordedRunner(result=runner_module.CommandOutput, outputs=_fenced_outputs())

    assert packages.run_package_step(inputs=inputs, runner=clean).refusal is None
    simulated = _calls_named(runner=clean, argv=("apt-get", "-s"))
    assert len(simulated) == 1
    assert tuple(simulated[0].argv) == (
        "apt-get",
        "-s",
        "install",
        "--no-install-recommends",
        "--no-remove",
        "docker.io=29.1.3-0ubuntu4.1",
        "containerd=2.2.2-0ubuntu1.1",
    )

    for answer, expected in (
        (
            _SIMULATION_CLEAN + "Inst runc (1.4.0-0ubuntu1 Ubuntu:24.04/noble [amd64])\n",
            "runc=1.4.0-0ubuntu1",
        ),
        (_SIMULATION_CLEAN + "Remv containerd [1.7.27-0ubuntu1]\n", "removes containerd"),
        (
            _SIMULATION_CLEAN
            + "Inst libc6 [2.39-0ubuntu8.3] (2.39-0ubuntu8.4 Ubuntu:24.04/noble-updates)\n",
            "upgrades the installed libc6",
        ),
    ):
        runner = _RecordedRunner(
            result=runner_module.CommandOutput,
            outputs=[(("apt-get", "-s"), [answer]), (("dpkg-query",), [_QUERY_BEFORE])],
        )

        outcome = packages.run_package_step(inputs=inputs, runner=runner)

        assert outcome.refusal is not None
        assert expected in outcome.refusal
        assert _calls_named(runner=runner, argv=("dpkg", "-i")) == []


def test_the_package_step_requires_the_post_install_difference_to_be_the_additions(
    tmp_path: Path,
) -> None:
    """Specification "Package fence": the difference MUST be the audited additions.

    The audit cleared one transaction; the `dpkg-query` difference across
    the install is the only evidence that the transaction which actually
    ran was that one. A dpkg run that landed a package nobody audited — a
    dependency unpacked from a stale archive in the cache, a resolver
    decision the simulation did not predict — leaves the host carrying it
    and raises no other signal whatever, so the difference is compared
    against the additions rather than merely inspected for the ones
    expected.
    """
    assert _RUNNER_PATH.is_file()
    runner_module = importlib.import_module(_RUNNER_MODULE)
    packages = importlib.import_module(_PACKAGES_MODULE)
    inputs = _declare(root=tmp_path, payload=_payload(cache=tmp_path / "cache"))
    unaudited = _QUERY_AFTER + "runc 1.4.0-0ubuntu1 installed\n"
    runner = _RecordedRunner(
        result=runner_module.CommandOutput,
        outputs=[(("dpkg-query",), [_QUERY_BEFORE, unaudited])],
    )

    outcome = packages.run_package_step(inputs=inputs, runner=runner)

    assert outcome.refusal is not None
    assert "runc=1.4.0-0ubuntu1" in outcome.refusal
    assert outcome.installed == ()


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

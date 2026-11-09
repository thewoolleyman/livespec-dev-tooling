"""Fixture packages and a mutmut stand-in for the Rule-26 kill-matrix scenarios.

Real mutmut forks a worker per mutant, which crashes on macOS hosts, so the
engine's `python -m mutmut` resolves to a stand-in placed first on PYTHONPATH.
The stand-in reads `mutmut-fixture.json` from the directory it runs in:

- `results` lists every fixture mutant;
- `apply <id>` replaces the mutant's `old` text with its `new` text in its
  file, and exits 1 when `old` is absent (a mutant mutmut cannot apply);
- every apply is appended to the file `KILL_MATRIX_APPLY_LOG` names, so a
  scenario can count which mutants a run re-tested.

The same PYTHONPATH carries a `sitecustomize` that refuses every connection and
name lookup beyond loopback, so each scenario runs the engine and every test
process with outbound network access off.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

__all__: list[str] = [
    "APPLY_LOG_VARIABLE",
    "FixtureMutant",
    "KillMatrixFixture",
    "applied_mutants",
    "read_report",
]


_REPO_ROOT = Path(__file__).resolve().parents[2]
APPLY_LOG_VARIABLE = "KILL_MATRIX_APPLY_LOG"

_STAND_IN = """\
import json
import os
import pathlib
import sys

fixture = json.loads(pathlib.Path("mutmut-fixture.json").read_text(encoding="utf-8"))
command = sys.argv[1]
if command == "results":
    for identifier in fixture:
        print(f"    {identifier}: killed")
elif command == "apply":
    identifier = sys.argv[2]
    log = os.environ.get("KILL_MATRIX_APPLY_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as handle:
            handle.write(identifier + "\\n")
    mutant = fixture[identifier]
    path = pathlib.Path(mutant["path"])
    text = path.read_text(encoding="utf-8")
    if mutant["old"] not in text:
        sys.exit(1)
    path.write_text(text.replace(mutant["old"], mutant["new"], 1), encoding="utf-8")
"""

_NO_NETWORK = """\
import socket

_LOOPBACK = {"127.0.0.1", "::1", "localhost", ""}
_real_getaddrinfo = socket.getaddrinfo


def _refuse(host):
    raise OSError(f"outbound network access is disabled for the kill-matrix scenario: {host}")


def _host(address):
    return address[0] if isinstance(address, tuple) else address


class _LoopbackOnlySocket(socket.socket):
    def connect(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6) and _host(address) not in _LOOPBACK:
            _refuse(_host(address))
        return super().connect(address)

    def connect_ex(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6) and _host(address) not in _LOOPBACK:
            _refuse(_host(address))
        return super().connect_ex(address)


def _getaddrinfo(host, *args, **kwargs):
    if host not in _LOOPBACK and host is not None:
        _refuse(host)
    return _real_getaddrinfo(host, *args, **kwargs)


socket.socket = _LoopbackOnlySocket
socket.getaddrinfo = _getaddrinfo
"""

_PYPROJECT = """\
[project]
name = "calc"
version = "0.0.0"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
"""


@dataclass(frozen=True, kw_only=True)
class FixtureMutant:
    """One mutant: replace `old` with `new` once in the file at `path`."""

    path: str
    old: str
    new: str


@dataclass(frozen=True, kw_only=True)
class KillMatrixFixture:
    """A fixture package plus the stand-in environment the engine runs under."""

    package: Path
    stubs: Path
    apply_log: Path

    @classmethod
    def create(
        cls,
        *,
        root: Path,
        sources: dict[str, str],
        tests: dict[str, str],
        mutants: dict[str, FixtureMutant],
    ) -> KillMatrixFixture:
        """Write the package, its mutant catalogue and the stand-ins under `root`."""
        stubs = root / "stubs"
        (stubs / "mutmut").mkdir(parents=True)
        _ = (stubs / "mutmut" / "__init__.py").write_text("", encoding="utf-8")
        _ = (stubs / "mutmut" / "__main__.py").write_text(_STAND_IN, encoding="utf-8")
        _ = (stubs / "sitecustomize.py").write_text(_NO_NETWORK, encoding="utf-8")
        package = root / "calc-package"
        package.mkdir()
        _ = (package / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
        fixture = cls(package=package, stubs=stubs, apply_log=root / "applied.log")
        _ = fixture.apply_log.write_text("", encoding="utf-8")
        fixture.write(files=sources | tests)
        fixture.set_mutants(mutants=mutants)
        return fixture

    def write(self, *, files: dict[str, str]) -> None:
        """Write (or overwrite) package files by package-relative path."""
        for relative, text in files.items():
            path = self.package / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            _ = path.write_text(text, encoding="utf-8")

    def set_mutants(self, *, mutants: dict[str, FixtureMutant]) -> None:
        """Replace the stand-in's mutant catalogue."""
        catalogue = {
            identifier: {"path": mutant.path, "old": mutant.old, "new": mutant.new}
            for identifier, mutant in mutants.items()
        }
        _ = (self.package / "mutmut-fixture.json").write_text(
            json.dumps(catalogue, indent=2), encoding="utf-8"
        )

    def environment(self) -> dict[str, str]:
        """Build a coverage-safe child environment with the stand-ins first."""
        removed = {
            "COVERAGE_PROCESS_START",
            "COV_CORE_CONFIG",
            "COV_CORE_DATAFILE",
            "COV_CORE_SOURCE",
            "PYTEST_ADDOPTS",
        }
        inherited = {key: value for key, value in os.environ.items() if key not in removed}
        return inherited | {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": os.pathsep.join(
                filter(None, (str(self.stubs), inherited.get("PYTHONPATH")))
            ),
            APPLY_LOG_VARIABLE: str(self.apply_log),
        }

    def run_engine(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        """Run the kill-matrix engine over the package, as the recipe does."""
        return self._run("livespec_dev_tooling.mutation_kill_matrix_runner", *arguments)

    def run_scheduled(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        """Run the scheduled entry point over the package, as a host timer does."""
        return self._run("livespec_dev_tooling.mutation_kill_matrix_scheduled", *arguments)

    def _run(self, module: str, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", "-m", module, str(self.package), *arguments],
            cwd=_REPO_ROOT,
            capture_output=True,
            check=False,
            env=self.environment(),
            text=True,
        )


def read_report(*, package: Path, name: str = "mutation-kill-matrix.json") -> dict[str, object]:
    """Read one of the engine's JSON documents from the package's reports directory."""
    loaded: dict[str, object] = json.loads((package / "reports" / name).read_text(encoding="utf-8"))
    return loaded


def applied_mutants(*, fixture: KillMatrixFixture) -> list[str]:
    """Every mutant identifier the stand-in was asked to apply, in order."""
    return fixture.apply_log.read_text(encoding="utf-8").split()

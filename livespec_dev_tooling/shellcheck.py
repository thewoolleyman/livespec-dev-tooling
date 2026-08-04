"""Policy-neutral ShellCheck substrate for tracked shell files.

The substrate deliberately stops at discovery and normalized execution output:
it does not decide severity floors, baselines, or whether findings fail a
governed repo. Callers get deterministic `(path, code, severity)` records from
the fleet-pinned ShellCheck binary and can layer policy separately.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias, cast

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.result import Failure, Result, Success  # noqa: E402

__all__: list[str] = [
    "ShellCheckUnavailable",
    "ShellCorpusEmpty",
    "ShellFinding",
    "discover_tracked_shell_files",
    "run_shellcheck",
]

_SHELLCHECK_VERSION = "0.11.0"
_SHELL_SUFFIXES = frozenset({".bash", ".bats", ".sh"})


@dataclass(frozen=True, kw_only=True)
class ShellFinding:
    path: Path
    code: str
    severity: str


@dataclass(frozen=True, kw_only=True)
class ShellCorpusEmpty:
    repo_root: Path


@dataclass(frozen=True, kw_only=True)
class ShellCheckUnavailable:
    binary_name: str
    required_version: str
    remedy: str


ShellDiscoveryResult: TypeAlias = Result[tuple[Path, ...], None]
ShellCheckRunFailure: TypeAlias = ShellCorpusEmpty | ShellCheckUnavailable
ShellCheckRunResult: TypeAlias = Result[tuple[ShellFinding, ...], ShellCheckRunFailure]


def _decode_git_paths(*, stdout: bytes) -> tuple[Path, ...]:
    paths = [Path(raw) for raw in stdout.decode("utf-8").split("\0") if raw]
    return tuple(sorted(path for path in paths if path.suffix in _SHELL_SUFFIXES))


def discover_tracked_shell_files(*, repo_root: Path) -> ShellDiscoveryResult:
    git_binary = cast(str, shutil.which("git"))
    # S603: argv uses a resolved `git` binary plus literal flags; no shell input.
    completed = subprocess.run(  # noqa: S603
        [git_binary, "ls-files", "-z"],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    return Success(_decode_git_paths(stdout=completed.stdout))


def _shellcheck_unavailable(*, shellcheck_bin: str) -> ShellCheckUnavailable:
    return ShellCheckUnavailable(
        binary_name=shellcheck_bin,
        required_version=_SHELLCHECK_VERSION,
        remedy=(
            "install ShellCheck 0.11.0 and expose it on PATH, for example with "
            "`mise install shellcheck@0.11.0` from the consumer repo"
        ),
    )


def _verify_shellcheck_version(*, binary: str) -> None:
    # S603: argv uses a resolved ShellCheck binary plus a literal version flag.
    completed = subprocess.run(  # noqa: S603
        [binary, "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    output = completed.stdout + completed.stderr
    _ = output.index(f"version: {_SHELLCHECK_VERSION}")


def _comment_finding(*, comment: Mapping[str, object]) -> ShellFinding:
    code_value = cast(int, comment["code"])
    return ShellFinding(
        path=Path(cast(str, comment["file"])),
        code=f"SC{code_value:04d}",
        severity=cast(str, comment["level"]),
    )


def _findings_from_json(*, stdout: str) -> ShellCheckRunResult:
    payload = cast(Mapping[str, object], json.loads(stdout))
    raw_comments = cast(list[Mapping[str, object]], payload["comments"])
    findings = [_comment_finding(comment=comment) for comment in raw_comments]
    return Success(tuple(sorted(findings, key=lambda item: (item.path, item.code, item.severity))))


def run_shellcheck(*, repo_root: Path, shellcheck_bin: str = "shellcheck") -> ShellCheckRunResult:
    shell_files = discover_tracked_shell_files(repo_root=repo_root).unwrap()
    if not shell_files:
        return Failure(ShellCorpusEmpty(repo_root=repo_root))
    binary = shutil.which(shellcheck_bin)
    if binary is None:
        return Failure(_shellcheck_unavailable(shellcheck_bin=shellcheck_bin))
    _verify_shellcheck_version(binary=binary)
    # S603: argv uses resolved ShellCheck, literal flags, and git-tracked paths.
    completed = subprocess.run(  # noqa: S603
        [binary, "--format=json1", "--norc", *[str(path) for path in shell_files]],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return _findings_from_json(stdout=completed.stdout)

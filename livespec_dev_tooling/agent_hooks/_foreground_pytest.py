"""_foreground_pytest — decide whether a FOREGROUND pytest is a full suite to refuse.

The ratified `SPECIFICATION/contracts.md` section "Agent-session
gate-command guard" refuses an agent session's foreground full-suite pytest
on a delegating host, naming the `just gate-start -- <command>` form, because
such a run can outlast the harness's tool-call ceiling and leave no verdict.
This module is that refusal's classifier; `pretooluse_background_guard`
logs and returns the verdict. It sits beside `_foreground_gate`, the git
refusal's classifier, and reads commands through the same
`_command_shape.invocations` parse, so a prefix, a separator or a `bash -c`
script cannot hide a pytest from one guard that the other would see
(livespec-dev-tooling-4pchid's review finding).
"""

from __future__ import annotations

import re
import shlex
from fnmatch import fnmatchcase
from pathlib import Path

from livespec_dev_tooling.agent_hooks._command_shape import Invocation, invocations
from livespec_dev_tooling.config import load_gate_job_only_tests
from livespec_dev_tooling.gate_command import pytest_command
from livespec_dev_tooling.gate_credential import gates_kubeconfig_readable
from livespec_dev_tooling.gate_remote_delegate import delegated_gate_enabled

__all__: list[str] = [
    "foreground_full_suite_pytest",
    "foreground_gate_job_only_pytest",
]

# Options that take a separate value argument. The list narrows what is read
# as a test path; the existing-path test in `_names_test_path` is what decides
# it, so an option missing here is still not mistaken for a targeted run.
_PYTEST_VALUE_OPTIONS: frozenset[str] = frozenset(
    {
        "-c",
        "--config-file",
        "--confcutdir",
        "--rootdir",
        "-o",
        "--override-ini",
        "-p",
        "-W",
        "--pythonwarnings",
        "-k",
        "-m",
        "-r",
        "--tb",
        "--maxfail",
        "--deselect",
        "--ignore",
        "--ignore-glob",
        "--durations",
        "--durations-min",
        "--junitxml",
        "--junit-xml",
        "--junitprefix",
        "--junit-prefix",
        "--basetemp",
        "--import-mode",
        "--capture",
        "--color",
        "--code-highlight",
        "--assert",
        "--show-capture",
        "--verbosity",
        "--log-level",
        "--log-format",
        "--log-date-format",
        "--log-file",
        "--log-file-level",
        "--log-file-format",
        "--log-file-date-format",
        "--log-cli-level",
        "--log-cli-format",
        "--log-cli-date-format",
        "--doctest-glob",
        "--doctest-report",
        "--cov",
        "--cov-config",
        "--cov-report",
        "--cov-fail-under",
        "--cov-context",
        "--dist",
        "--tx",
        "--rsyncdir",
        "--maxprocesses",
        "--max-worker-restart",
        "--timeout",
        "--timeout-method",
        "--reruns",
        "--reruns-delay",
        "--only-rerun",
        "--rerun-except",
        "--randomly-seed",
        "--hypothesis-seed",
        "--hypothesis-profile",
    }
)

_HEREDOC_BODY: re.Pattern[str] = re.compile(
    r"<<-?\s*(?P<quote>['\"]?)(?P<delimiter>[A-Za-z_][A-Za-z0-9_]*)"
    r"(?P=quote)[^\n]*\n.*?^(?P=delimiter)[ \t]*$",
    re.DOTALL | re.MULTILINE,
)


def foreground_full_suite_pytest(*, command: str, cwd: Path) -> Path | None:
    """The repository an eligible host's foreground full-suite pytest targets, or None.

    Reads `command` through `invocations`, the parse the foreground git guard
    uses, so an environment prefix, `nohup`, `mise exec --` or a `bash -c`
    script hides no pytest, and a pytest after `;` or `&&` is still found. The
    target repository is decided as for a git command: each `cd <path>` moves
    it, and any pytest reached before a `cd` targets the session's working
    directory. EVERY pytest is judged, each against the target in force when
    the shell reaches it, so a targeted pytest ahead of a full one hides
    nothing; the first eligible full suite decides the verdict. Text the shell
    cannot lex (an unterminated quote) runs nothing at all, so it is not
    refused.
    """
    try:
        parsed_command = _without_heredoc_bodies(command=command)
        _ = shlex.split(parsed_command)
    except ValueError:
        return None
    target = cwd
    for invocation in invocations(command=parsed_command):
        if invocation.binary == "cd":
            target = _cd_target(
                cwd=cwd,
                target=target,
                cd_target=invocation.subcommand,
            )
            continue
        pytest_argv = pytest_command(command=_argv(invocation=invocation))
        if pytest_argv is not None:
            eligible = (
                _is_full_suite_pytest(pytest_argv=pytest_argv, cwd=target)
                and delegated_gate_enabled(repo_root=target)
                and gates_kubeconfig_readable()
            )
            if eligible:
                return target
    return None


def foreground_gate_job_only_pytest(*, command: str, cwd: Path) -> Path | None:
    """Return the eligible repository a declared gate-Job-only pytest targets."""
    try:
        parsed_command = _without_heredoc_bodies(command=command)
        _ = shlex.split(parsed_command)
    except ValueError:
        return None
    target = cwd
    for invocation in invocations(command=parsed_command):
        if invocation.binary == "cd":
            target = _cd_target(cwd=cwd, target=target, cd_target=invocation.subcommand)
            continue
        pytest_argv = pytest_command(command=_argv(invocation=invocation))
        if pytest_argv is None or not _eligible_gate_job_only_repository(cwd=target):
            continue
        if _pytest_targets_declared_gate_job_only(pytest_argv=pytest_argv, cwd=target):
            return target
    return None


def _eligible_gate_job_only_repository(*, cwd: Path) -> bool:
    return (
        delegated_gate_enabled(repo_root=cwd)
        and gates_kubeconfig_readable()
        and bool(load_gate_job_only_tests(repo_root=cwd))
    )


def _pytest_targets_declared_gate_job_only(*, pytest_argv: tuple[str, ...], cwd: Path) -> bool:
    globs = load_gate_job_only_tests(repo_root=cwd)
    return any(
        _path_matches_gate_job_only_glob(path=path, cwd=cwd, globs=globs)
        for target in _explicit_test_targets(pytest_argv=pytest_argv, cwd=cwd)
        for path in _test_modules_under(target=target)
    )


def _explicit_test_targets(*, pytest_argv: tuple[str, ...], cwd: Path) -> tuple[Path, ...]:
    paths: list[Path] = []
    expect_option_value = False
    for argument in pytest_argv[1:]:
        if expect_option_value:
            expect_option_value = False
        elif argument in _PYTEST_VALUE_OPTIONS:
            expect_option_value = True
        elif not argument.startswith("-") and _names_test_path(argument=argument, cwd=cwd):
            paths.append(cwd / argument.split("::", maxsplit=1)[0])
    return tuple(paths)


def _test_modules_under(*, target: Path) -> tuple[Path, ...]:
    if target.is_file():
        return (target,)
    if target.is_dir():
        return tuple(sorted(target.rglob("test_*.py")))
    return ()


def _path_matches_gate_job_only_glob(*, path: Path, cwd: Path, globs: tuple[str, ...]) -> bool:
    try:
        relative = path.relative_to(cwd).as_posix()
    except ValueError:
        return False
    return any(fnmatchcase(relative, pattern) for pattern in globs)


def _cd_target(*, cwd: Path, target: Path, cd_target: str | None) -> Path:
    """Resolve a literal `cd` target, or use the session cwd when it is opaque."""
    if cd_target is None:
        return Path.home()
    if "$" in cd_target or "`" in cd_target:
        return cwd
    return target / Path(cd_target).expanduser()


def _without_heredoc_bodies(*, command: str) -> str:
    """Replace heredoc bodies with separators before reading command positions."""
    return _HEREDOC_BODY.sub(";", command)


def _argv(*, invocation: Invocation) -> tuple[str, ...]:
    """Rebuild an invocation's words in shell order, as `pytest_command` reads them."""
    head = (invocation.subcommand,) if invocation.subcommand is not None else ()
    return (invocation.binary, *invocation.options, *head, *invocation.args)


def _is_full_suite_pytest(*, pytest_argv: tuple[str, ...], cwd: Path) -> bool:
    """A pytest names no test path, unless xdist makes it full-suite anyway."""
    arguments = pytest_argv[1:]
    if any(_is_numprocesses_option(argument=argument) for argument in arguments):
        return True
    expect_option_value = False
    for argument in arguments:
        if expect_option_value:
            expect_option_value = False
        elif argument in _PYTEST_VALUE_OPTIONS:
            expect_option_value = True
        elif not argument.startswith("-") and _names_test_path(argument=argument, cwd=cwd):
            return False
    return True


def _names_test_path(*, argument: str, cwd: Path) -> bool:
    """A positional argument is a test path when it is a node id or exists on disk."""
    return "::" in argument or (cwd / argument).exists()


def _is_numprocesses_option(*, argument: str) -> bool:
    """xdist's worker count, spelled `-n 4`, `-n4`, `-n=4` or `--numprocesses[=4]`."""
    return argument.startswith(("-n", "--numprocesses"))

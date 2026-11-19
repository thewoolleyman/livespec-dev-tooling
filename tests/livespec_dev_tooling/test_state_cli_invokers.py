"""A committed invoker of a state-writing CLI must pass every one of its state-location flags.

Governing specification: `SPECIFICATION/non-functional-requirements.md` section
"Testing approach", bullet "Host-state isolation of CLIs", and the scenario "a
committed invoker that omits a state-writing CLI's state-path flag fails the
test suite" in `SPECIFICATION/scenarios.md`.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULE = "livespec_dev_tooling.state_cli_invokers"
_MODULE_PATH = _REPO_ROOT / "livespec_dev_tooling" / "state_cli_invokers.py"

_COMPLETE_ARGV = """\
- name: Run a guard operation
  ansible.builtin.command:
    argv:
      - systemd-run
      # The guard has no default for either root, so every operation names them.
      - "{{ docker_engine_guard_executable }}"
      - "{{ docker_engine_op }}"
      - --state-root
      - "{{ docker_engine_state_root }}"
      - --runtime-root
      - "{{ docker_engine_runtime_root }}"
"""


def _scanner() -> Any:
    """The scanner module, once its file is known to exist."""
    assert _MODULE_PATH.is_file()
    return importlib.import_module(_MODULE)


def _write(*, root: Path, relative: str, text: str) -> None:
    """Commit-equivalent: put one file at `relative` under `root`."""
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    _ = target.write_text(text, encoding="utf-8")


def _missing(*, root: Path) -> list[tuple[str, str]]:
    """Every (invoker file, missing flag) pair the scanner reports under `root`."""
    found = _scanner().find_unflagged_invokers(root=root)
    return sorted((invoker.path, invoker.flag) for invoker in found)


def test_an_ansible_argv_that_omits_the_runtime_root_is_named_with_its_file_and_flag(
    *, tmp_path: Path
) -> None:
    """A guard invocation without `--runtime-root` is reported by file and flag."""
    argv = _COMPLETE_ARGV.replace(
        '      - --runtime-root\n      - "{{ docker_engine_runtime_root }}"\n', ""
    )
    _write(root=tmp_path, relative="ansible/guard_op.yml", text=argv)

    assert _missing(root=tmp_path) == [("ansible/guard_op.yml", "--runtime-root")]


def test_an_invoker_that_omits_every_flag_is_reported_once_per_missing_flag(
    *, tmp_path: Path
) -> None:
    """Both of the guard's roots are named when neither is passed."""
    _write(
        root=tmp_path,
        relative="scripts/run.sh",
        text="sudo /usr/local/libexec/docker-engine-guard rollback run-a\n",
    )

    assert _missing(root=tmp_path) == [
        ("scripts/run.sh", "--runtime-root"),
        ("scripts/run.sh", "--state-root"),
    ]


def test_an_invoker_that_passes_every_flag_is_not_reported(*, tmp_path: Path) -> None:
    """The complete argv, with a comment between its items, is clean."""
    _write(root=tmp_path, relative="ansible/guard_op.yml", text=_COMPLETE_ARGV)

    assert _missing(root=tmp_path) == []


def test_flags_listed_before_the_cli_in_an_argv_count(*, tmp_path: Path) -> None:
    """A preflight argv that names its root ahead of the module path is clean."""
    argv = """\
- ansible.builtin.command:
    argv:
      - --state-root
      - /var/lib/docker-engine-guard
      - /x/_docker_engine_guard_preflight_cli.py
      - record
"""
    _write(root=tmp_path, relative="ansible/pre.yml", text=argv)

    assert _missing(root=tmp_path) == []


def test_a_preflight_argv_without_a_state_root_is_reported(*, tmp_path: Path) -> None:
    """The preflight CLI has its own, smaller, set of state-location flags."""
    argv = """\
- ansible.builtin.command:
    argv:
      - /x/_docker_engine_guard_preflight_cli.py
      - refusals
      - --declared
      - /tmp/declared.json
"""
    _write(root=tmp_path, relative="ansible/pre.yml", text=argv)

    assert _missing(root=tmp_path) == [("ansible/pre.yml", "--state-root")]


def test_a_systemd_unit_that_omits_the_state_dir_is_reported(*, tmp_path: Path) -> None:
    """The flake-retry filer's `--state-dir` is checked in a unit template."""
    unit = (
        "[Service]\n"
        "ExecStart=/usr/bin/python -m livespec_dev_tooling.flake_retry_filer --repo-root /r\n"
    )
    _write(root=tmp_path, relative="roles/filer/templates/filer.service.j2", text=unit)

    assert _missing(root=tmp_path) == [("roles/filer/templates/filer.service.j2", "--state-dir")]


def test_a_systemd_unit_that_passes_the_state_dir_equals_form_is_clean(*, tmp_path: Path) -> None:
    """`--flag=value` counts as passing the flag."""
    unit = "ExecStart=python -m livespec_dev_tooling.flake_retry_filer --state-dir=/s\n"
    _write(root=tmp_path, relative="x.service", text=unit)

    assert _missing(root=tmp_path) == []


def test_a_shell_continuation_line_carries_the_flags_of_its_command(*, tmp_path: Path) -> None:
    """Flags on backslash-continued lines belong to the invocation that started them."""
    complete = (
        "sudo /usr/local/libexec/docker-engine-guard rollback run-a \\\n"
        "  --state-root /s \\\n"
        "  --runtime-root /r\n"
        "echo done\n"
    )
    short = (
        "sudo /usr/local/libexec/docker-engine-guard rollback run-a \\\n"
        "  --state-root /s\n"
        "echo --runtime-root\n"
    )
    _write(root=tmp_path, relative="a/complete.sh", text=complete)
    _write(root=tmp_path, relative="a/short.sh", text=short)

    assert _missing(root=tmp_path) == [("a/short.sh", "--runtime-root")]


def test_a_help_invocation_is_exempt(*, tmp_path: Path) -> None:
    """`--help` prints usage and writes nothing, so it names no state location."""
    _write(
        root=tmp_path,
        relative="ansible/install.yml",
        text='- ansible.builtin.command:\n    argv: ["{{ docker_engine_guard_executable }}", --help]\n',
    )
    _write(root=tmp_path, relative="a/help.sh", text="/usr/local/libexec/docker-engine-guard -h\n")

    assert _missing(root=tmp_path) == []


def test_mentions_that_are_not_invocations_are_ignored(*, tmp_path: Path) -> None:
    """Variable definitions, `dest:` keys, comments and process patterns invoke nothing."""
    _write(
        root=tmp_path,
        relative="ansible/defaults.yml",
        text=(
            "docker_engine_guard_executable: /usr/local/libexec/docker-engine-guard\n"
            "# /usr/local/libexec/docker-engine-guard <op> <run>\n"
            '- dest: "{{ docker_engine_guard_executable }}"\n'
        ),
    )
    _write(root=tmp_path, relative="a/pgrep.sh", text="pgrep -f docker_engine_guard.py rollback\n")
    _write(
        root=tmp_path, relative="a/comment.sh", text="# /usr/local/libexec/docker-engine-guard\n"
    )

    assert _missing(root=tmp_path) == []


def test_files_outside_the_invoker_kinds_and_trees_are_not_scanned(*, tmp_path: Path) -> None:
    """Prose, specifications, tests and vendored trees may quote an invocation."""
    bare = "/usr/local/libexec/docker-engine-guard rollback run-a\n"
    _write(root=tmp_path, relative="docs/guide.md", text=bare)
    _write(root=tmp_path, relative="docs/run.sh", text=bare)
    _write(root=tmp_path, relative="tests/run.sh", text=bare)
    _write(root=tmp_path, relative=".venv/lib/run.sh", text=bare)
    _write(root=tmp_path, relative="ansible/notes.txt", text=bare)

    assert _missing(root=tmp_path) == []


def test_a_finding_names_the_invoker_file_the_line_and_the_missing_flag(*, tmp_path: Path) -> None:
    """The message a failing suite shows names where to look and what to add."""
    _write(
        root=tmp_path,
        relative="a/run.sh",
        text="echo start\n/usr/local/libexec/docker-engine-guard arm run-a --state-root /s\n",
    )

    (found,) = _scanner().find_unflagged_invokers(root=tmp_path)

    assert (found.path, found.line, found.flag) == ("a/run.sh", 2, "--runtime-root")
    message = found.render()
    assert "a/run.sh" in message
    assert "--runtime-root" in message


@pytest.mark.parametrize(
    ("relative", "removed"),
    [
        ("ansible/roles/docker_engine/tasks/guard_op.yml", "--runtime-root"),
        ("ansible/roles/docker_engine/tasks/fresh_run.yml", "--state-root"),
        (
            "ansible/roles/flake_retry_filer/templates/livespec-flake-retry-filer.service.j2",
            "--state-dir",
        ),
    ],
)
def test_dropping_a_flag_from_a_committed_invoker_fails_the_scan(
    *, relative: str, removed: str, tmp_path: Path
) -> None:
    """Removing the flag from the real invoker makes the scan name that file and flag."""
    text = (_REPO_ROOT / relative).read_text(encoding="utf-8")
    assert removed in text
    _write(root=tmp_path, relative=relative, text=text.replace(removed, "--elided"))

    assert (relative, removed) in _missing(root=tmp_path)


def test_every_committed_invoker_passes_each_of_its_state_location_flags() -> None:
    """The repository's own units, tasks, templates and scripts pass the now-required flags."""
    found = _scanner().find_unflagged_invokers(root=_REPO_ROOT)

    assert [invoker.render() for invoker in found] == []

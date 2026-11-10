"""ansible_get_url_checksum — a role's `get_url` pins a checksum or records why it need not.

`ansible.builtin.get_url` does not download under `--check`. With no `checksum:`
it compares the destination it finds against an EMPTY temporary file, so the task
reports `changed` against a host that is already converged, and the drift report
this tree exists to produce carries a permanent false positive
(livespec-dev-tooling-7g5qba: the onepassword_desktop debsig policy, measured on
hetzner-xubuntu 2026-11-08 with the SHA-1 of an empty file as `checksum_src`).
With a `checksum:` the module hashes the existing destination first and exits
`ok` without any download when it matches, under both `--check` and a real apply.

The rule, over every task file under `ansible/roles/*/tasks`:

- A `get_url` task MUST carry a non-empty `checksum:` (a literal digest, a
  templated one, or a `sha256:<url>` the module fetches itself), OR
- the task MUST record an exemption, a comment line anywhere in the task of the
  form `# check-mode-exempt: <why check mode cannot report it falsely>`. The
  reason is mandatory; an exemption that names none is a finding. The honest
  reasons are the ones where the task never runs under `--check` (it is gated on
  `not ansible_check_mode`) or never has an existing destination to compare.

A tree in which no `get_url` task is found reports itself vacuous rather than as a
pass, so a move of the roles cannot turn this check into a silent no-op.

The scan is line-based, like its sibling `ansible_hostname_free`, and reads the
module key spelled `get_url`, `ansible.builtin.get_url` or `ansible.legacy.get_url`.
It does not read playbooks at `ansible/*.yml`: a drill playbook is not part of the
drift report, and the obligation is the roles'.

Repo-private check: the module lives OUTSIDE `livespec_dev_tooling/checks/` so it
stays out of the canonical (fleet-universal) slug set. Wired into this repo's
justfile `check:` aggregate (repo-private block).

Output discipline: structlog JSON to stderr; no `print`, no `sys.stderr.write`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import NamedTuple

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = []


_ROLES_DIR = Path("ansible") / "roles"
_TASK_GLOBS = ("*/tasks/**/*.yml", "*/tasks/**/*.yaml")

_GET_URL = re.compile(r"^(\s*(?:-\s+)?)(?:ansible\.(?:builtin|legacy)\.)?get_url:(.*)$")
_TASK_NAME = re.compile(r"^\s*(?:-\s+)?name:\s*(\S.*?)\s*$")
_CHECKSUM_KEY = re.compile(r"^(\s*)checksum:\s*(.*?)\s*$")
_INLINE_CHECKSUM = re.compile(r"\bchecksum=\S")
_EXEMPTION = re.compile(r"^\s*#\s*check-mode-exempt:\s*(\S.*)$")
_EMPTY_SCALARS = ("", "''", '""')

_REMEDIATION = (
    "pin the vendor's digest with `checksum: sha256:<digest>` so the module hashes the "
    "existing file and reports ok without downloading, under --check and on apply; or, "
    "when check mode genuinely cannot report the task falsely, add a comment line to the "
    "task, `# check-mode-exempt: <why>`, naming the reason"
)


class Finding(NamedTuple):
    kind: str
    path: str
    line: int
    task: str


def _indent(*, line: str) -> int:
    return len(line) - len(line.lstrip())


def _is_code(*, line: str) -> bool:
    return bool(line.strip()) and not line.lstrip().startswith("#")


def _block_end(*, lines: list[str], start: int, key_indent: int, deeper: bool) -> int:
    """Return the index one past the run of lines from `start` that stay inside a key's block.

    A line stays inside while it is blank, a comment, or indented at least as far as
    the key (`deeper` False) or strictly further (`deeper` True).
    """
    floor = key_indent if deeper else key_indent - 1
    end = start
    while end < len(lines) and (not _is_code(line=lines[end]) or _indent(line=lines[end]) > floor):
        end += 1
    return end


def _task_lines(
    *, lines: list[str], module_index: int, key_indent: int, dash_led: bool
) -> list[str]:
    """Return the lines of the task whose module key sits at `module_index`.

    A nameless task carries the module key on its own dash line, so the task opens
    there. Otherwise it opens at the nearest line above whose indent is below the
    module key's (its `- name:` dash). It closes at the first code line below whose
    indent is below the key's again (the next task); trailing comments belong to
    that next task.
    """
    start = module_index
    if not dash_led:
        start = next(
            (
                index
                for index in range(module_index - 1, -1, -1)
                if _is_code(line=lines[index]) and _indent(line=lines[index]) < key_indent
            ),
            0,
        )
    end = _block_end(lines=lines, start=module_index + 1, key_indent=key_indent, deeper=False)
    while not _is_code(line=lines[end - 1]):
        end -= 1
    return lines[start:end]


def _is_pinned(*, lines: list[str], module_index: int, key_indent: int, inline: str) -> bool:
    if _INLINE_CHECKSUM.search(inline):
        return True
    end = _block_end(lines=lines, start=module_index + 1, key_indent=key_indent, deeper=True)
    code = [line for line in lines[module_index + 1 : end] if _is_code(line=line)]
    argument_indent = min((_indent(line=line) for line in code), default=0)
    for line in code:
        match = _CHECKSUM_KEY.match(line)
        if match is None or _indent(line=line) != argument_indent:
            continue
        return match.group(2) not in _EMPTY_SCALARS
    return False


def _file_findings(*, path: str, source: str) -> tuple[int, list[Finding]]:
    lines = source.splitlines()
    inspected = 0
    findings: list[Finding] = []
    for number, raw in enumerate(lines):
        match = _GET_URL.match(raw)
        if match is None or not _is_code(line=raw):
            continue
        inspected += 1
        key_indent = len(match.group(1))
        task = _task_lines(
            lines=lines, module_index=number, key_indent=key_indent, dash_led="-" in match.group(1)
        )
        if any(_EXEMPTION.match(line) for line in task):
            continue
        if _is_pinned(
            lines=lines, module_index=number, key_indent=key_indent, inline=match.group(2)
        ):
            continue
        name = next((m.group(1) for m in map(_TASK_NAME.match, task) if m is not None), "")
        findings.append(Finding(kind="unpinned-get-url", path=path, line=number + 1, task=name))
    return inspected, findings


def _findings(*, cwd: Path) -> list[Finding]:
    inspected = 0
    findings: list[Finding] = []
    roles = cwd / _ROLES_DIR
    paths = sorted({path for glob in _TASK_GLOBS for path in roles.glob(glob)})
    for path in paths:
        count, found = _file_findings(
            path=str(path.relative_to(cwd)), source=path.read_text(encoding="utf-8")
        )
        inspected += count
        findings.extend(found)
    if inspected == 0:
        findings.append(Finding(kind="vacuous", path=str(_ROLES_DIR), line=0, task=""))
    return findings


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("ansible_get_url_checksum")
    findings = _findings(cwd=Path.cwd())
    for finding in findings:
        log.error(
            "role get_url task can report a false change under --check"
            if finding.kind == "unpinned-get-url"
            else "no get_url task was inspected, so this check proved nothing",
            path=finding.path,
            line=finding.line,
            kind=finding.kind,
            task=finding.task,
            remediation=_REMEDIATION,
        )
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())

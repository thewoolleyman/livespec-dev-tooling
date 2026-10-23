"""dev_host_fabro_client_bins_declared — every committed `bin` names a staged path.

This repository's `SPECIFICATION/non-functional-requirements.md` states how a dev
host carries pinned Fabro client builds (v088), and its "Committed bins name a
declared path" clause is what this check asserts: every
`dispatcher.factories.<name>.bin` this repository commits in its root
`.livespec.jsonc` MUST equal the `path` of one `fabro_client_builds` entry of
`ansible/inventory/group_vars/dev_hosts.yml`, and this check MUST report itself
VACUOUS rather than as a pass when this repository commits no `bin`.

WHY THE RULE IS WORTH A CHECK. A committed `bin` is the file a Dispatcher
running natively on the dev host EXECS to reach a factory. One that names a path
the dev-host play does not stage is a routing table resting on a binary nobody
provisioned: it was put there by hand, no drift report sees it, and nothing can
say which build it is. The failure is silent in the direction that costs most —
the dispatch keeps working until that file is replaced, moved or rebuilt
differently, at which point every repository pointing at it is reaching a client
nobody chose.

WHY EQUALITY AND NOT RESOLUTION. The `fabro_client` role compares names on the
HOST, following symbolic links and comparing inodes, because that is the only
way to answer "is this the same file". This check cannot: it reads two committed
TEXTS and has no host to resolve them against, and a check that resolved them
against whichever machine it happened to run on would grade that machine instead
of the tree — the shape `tests_host_path_free` exists to refuse. So the
obligation asserted here is the one the clause states, textual equality, and the
host-side question stays with the role.

WHY EVERY ARM THAT CANNOT READ ITS INPUT REFUSES. An absent configuration, one
that will not parse, and an absent declaration file beside a committed `bin` are
all readings that were never taken. Each has an obvious wrong answer which is
also a PASS — "this repository commits no bin", "no path is declared" — and both
read as green from the exit status alone. So each is a named refusal instead.

WHY THE DECLARATION READER IS BLOCK-SCOPED. `dev_hosts.yml` is the group's whole
variable file, shared with every other role's values, and more than one of them
carries a `path` key. A reader that took every `path:` in the file would accept a
`bin` the `fabro_client` role never stages — this check certifying the wrong
file, which is worse than not having it at all.

Repo-private check: the module lives OUTSIDE `livespec_dev_tooling/checks/` so it
stays out of the canonical (fleet-universal) slug set. The clause says why in as
many words — it reads THIS repository's own `.livespec.jsonc` against THIS
repository's own inventory, and a canonical slug would oblige nine siblings to
wire a check about a file they do not have. Wired into this repo's justfile
`check:` aggregate (repo-private block).

Output discipline: structlog JSON to stderr; no `print`, no `sys.stderr.write`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, NamedTuple, cast

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import jsoncomment  # noqa: E402  — vendor-path-aware import after sys.path insert.
import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = []


_CONFIG = Path(".livespec.jsonc")
_DECLARATION = Path("ansible/inventory/group_vars/dev_hosts.yml")

_DISPATCHER_KEY = "dispatcher"
_FACTORIES_KEY = "factories"
_BIN_KEY = "bin"
_BUILDS_KEY = "fabro_client_builds"

# The declaration block, read by INDENTATION rather than by a YAML parser: this
# package vendors no YAML reader, and the sibling `ansible_hostname_free` check
# reads this same inventory the same way. A line at column zero CLOSES the block,
# which is what keeps a later group value's own `path:` out of the result.
_BUILDS_OPENER = re.compile(rf"^{_BUILDS_KEY}:\s*$")
_COLUMN_ZERO = re.compile(r"^\S")
# An entry's `path` key, as a list item (`  - path: …`) or as a further key of one
# (`    path: …`). The `\s*` after the optional dash cannot consume a name prefix,
# so `source_path:` and `binary_path:` do not match.
_PATH_KEY = re.compile(r"^\s+-?\s*path:\s*(?P<value>[^#\s]+)")

_REMEDIATION = (
    "a committed `bin` must equal the `path` of one `fabro_client_builds` entry in "
    f"{_DECLARATION}, so the build a Dispatcher execs is the one the dev-host play "
    "stages from a digest-verified control-node source. Declare the entry (path, "
    "source and sha256) and converge `ansible/dev-host.yml`, or point the `bin` at a "
    "path already declared — never stage the file by hand"
)


class _Bin(NamedTuple):
    """One committed `dispatcher.factories.<name>.bin`."""

    factory: str
    path: str


def _document(*, path: Path) -> object | None:
    """The JSONC document `path` holds, or `None` when it cannot be read as one.

    The read and the parse share one handler because they are one question — does
    this file yield a document — and the caller reports the two apart by asking
    `is_file()` first. Nothing is logged here: a caller that reports the refusal
    keeps the narration in one place and keeps this a reading.
    """
    try:
        return jsoncomment.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return None


def _committed_bins(*, document: object) -> list[_Bin]:
    """Every `dispatcher.factories.<name>.bin` the document carries, in name order.

    The WHOLE document is walked rather than one known key path. The dispatcher
    block lives under the implementation plugin's own top-level key, and that key
    is the plugin's NAME: hard-coding it would make this check go quiet — a clean
    exit 0 reporting no committed bin — on the day a repository changes
    orchestrator, which is the day its routing is most worth checking.
    """
    found: list[_Bin] = []
    pending: list[object] = [document]
    while pending:
        node = pending.pop()
        if isinstance(node, list):
            pending.extend(cast("list[object]", node))
            continue
        if not isinstance(node, dict):
            continue
        mapping = cast("dict[str, Any]", node)
        pending.extend(mapping.values())
        found.extend(_bins_of(dispatcher=mapping.get(_DISPATCHER_KEY)))
    return sorted(found)


def _bins_of(*, dispatcher: object) -> list[_Bin]:
    """Every `bin` one `dispatcher` value declares across its factories."""
    if not isinstance(dispatcher, dict):
        return []
    factories = cast("dict[str, Any]", dispatcher).get(_FACTORIES_KEY)
    if not isinstance(factories, dict):
        return []
    found: list[_Bin] = []
    for name, factory in cast("dict[str, Any]", factories).items():
        if not isinstance(factory, dict):
            continue
        declared = cast("dict[str, Any]", factory).get(_BIN_KEY)
        if isinstance(declared, str) and declared:
            found.append(_Bin(factory=str(name), path=declared))
    return found


def _declared_paths(*, source: str) -> list[str]:
    """Every `path` the `fabro_client_builds` block declares, in declaration order."""
    paths: list[str] = []
    inside = False
    for raw in source.splitlines():
        if _BUILDS_OPENER.match(raw) is not None:
            inside = True
            continue
        if not inside:
            continue
        if _COLUMN_ZERO.match(raw) is not None:
            break
        if raw.lstrip().startswith("#"):
            continue
        key = _PATH_KEY.match(raw)
        if key is not None:
            paths.append(key.group("value").strip("\"'"))
    return paths


def _configured(*, cwd: Path, log: structlog.stdlib.BoundLogger) -> object | None:
    """This repository's root configuration, or `None` having named the refusal."""
    path = cwd / _CONFIG
    if not path.is_file():
        log.error(
            "the root configuration this check reads committed factory bins out of is "
            "absent, so whether any bin names an undeclared path was never established",
            kind="configuration-absent",
            path=str(_CONFIG),
            remediation=_REMEDIATION,
        )
        return None
    document = _document(path=path)
    if document is None:
        log.error(
            "the root configuration did not parse as JSONC, so the committed factory "
            "bins could not be read. This is a refusal rather than a pass: a "
            "configuration whose contents are unknown is not a configuration that "
            "commits no bin",
            kind="configuration-unparseable",
            path=str(_CONFIG),
            remediation=_REMEDIATION,
        )
    return document


def _declaration(
    *, cwd: Path, log: structlog.stdlib.BoundLogger, committed: list[_Bin]
) -> list[str] | None:
    """The declared paths, or `None` having named the refusal a committed bin earns."""
    path = cwd / _DECLARATION
    if path.is_file():
        return _declared_paths(source=path.read_text(encoding="utf-8"))
    log.error(
        "this repository commits a dispatcher factory bin and carries no inventory file "
        "to declare it in, so the build that bin names is staged by nothing",
        kind="declaration-file-absent",
        path=str(_DECLARATION),
        committed=[one.path for one in committed],
        remediation=_REMEDIATION,
    )
    return None


def _logger() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger("dev_host_fabro_client_bins_declared")


def main() -> int:
    """Refuse every committed `bin` that names no declared `fabro_client_builds` path."""
    log = _logger()
    cwd = Path.cwd()
    document = _configured(cwd=cwd, log=log)
    if document is None:
        return 1
    committed = _committed_bins(document=document)
    if not committed:
        log.warning(
            "vacuous: this repository commits no dispatcher factory bin, so this run "
            "inspected nothing — that every committed bin names a GitOps-staged path "
            "here is UNPROVEN, not proven. This is not a failure (a repository may "
            "legitimately reach every factory through the host PATH client), but an "
            "exit 0 from this check certifies nothing until one bin is committed",
            verdict="vacuous",
            path=str(_CONFIG),
        )
        return 0
    declared = _declaration(cwd=cwd, log=log, committed=committed)
    if declared is None:
        return 1
    undeclared = [one for one in committed if one.path not in declared]
    for one in undeclared:
        log.error(
            "a committed dispatcher factory bin names no declared Fabro client build "
            "path, so the file it execs is not one the dev-host play stages",
            kind="bin-names-no-declared-path",
            factory=one.factory,
            bin=one.path,
            declared=declared,
            remediation=_REMEDIATION,
        )
    return 1 if undeclared else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Shared `ConfigParseError` rendering for the check supervisors.

`SPECIFICATION/contracts.md` section "Configuration loader" makes
`ConfigParseError` an IO-layer exception that each check's `main()`
supervisor catches and renders as a structured diagnostic. Measured on
master `dd98bbb0`, exactly ONE of the 33 `load_config` call sites under
this package did that; the other 32 let the error escape as an uncaught
traceback.

That gap is worse than an unpolished message. A traceback reaches stderr
through the INTERPRETER rather than through structlog, so a check whose
job is to enforce this package's structlog-only output discipline
(`print` and `sys.*.write` are banned here) broke that discipline itself
at the one moment its diagnostic mattered — when the consumer's
`pyproject.toml` was malformed and the operator needed to be told which
key to fix.

This module is the SINGLE DEFINITION of that rendering, following the
promotion precedent `config.is_under_any_tree` and
`config.derive_source_prefixes` set: a shape a dozen checks need becomes
one shared definition rather than a dozen near-identical blocks. It
GENERALIZES `required_role_keys_declared.main()`, which is the one
compliant call site already in the tree, rather than inventing a second
diagnostic shape — same event wording, same fields, same non-zero
outcome. That module stays unmigrated and is pinned by a control test, so
any future divergence between the precedent and this generalization is
visible in one place.

There are TWO entry points because there are two ways a check reaches
the config, not because there are two diagnostics. `load_config_or_report`
serves the checks that load it themselves;
`resolve_check_context_or_report` serves the applies-to-all checks, whose
FIRST reach is the `load_config` buried inside `resolve_check_universe()`
— an earlier frame that a wrap of the check's own load line cannot see.
Both render through one private `_report_parse_failure`, so the single
definition survives the split.

It owes the RENDERING, not the REJECTION. The loader still raises loudly,
the caller still exits non-zero, and the raised message still names the
offending key and its blessed spellings; nothing a consumer's config is
rejected for today becomes accepted.

A RAILWAY VALUE RATHER THAN AN EXIT CODE is the return, for the reason
the `None` it replaces was chosen: the caller's non-zero is not always a
literal `1` — `check_mutation` returns it up through a gate that already
speaks in `int | None` — so the exit stays with the supervisor that owns
it, and a sentinel exit code would have had to be distinguishable from a
legitimately loaded `Config` anyway.

WHAT CHANGED AT `livespec-dev-tooling-qndn.17` is the other half of that
argument. `Config | None` spelled a FAILURE as an absence. The type said
only that there might be no config; it did not say that reading one had
been ATTEMPTED AND FAILED, so a caller was free to read `None` as
"nothing to work with" and carry on, and nothing would have objected.
Every one of the 33 supervisors happened to exit non-zero, which is what
kept the collapse inert — but that is a property of 33 call sites all
being written correctly, not a property the return type secured. A
failure track cannot be carried on by accident.

`IOResult` and not `Result`, because both entry points touch the world:
one reads the consumer's `pyproject.toml`, the other shells out to git
for the tracked-file universe. Claiming purity here would blur the
distinction the sibling conversions in this tree sharpened.

THE FAILURE TRACK CARRIES THE `ConfigParseError` THIS MODULE HAS ALREADY
RENDERED, and it is EVIDENCE rather than a second report. It names the
offending key and its blessed spellings, so a caller with a richer
verdict surface than an exit code can use it, and a caller that only
exits non-zero can leave it unread. ⛔ What a caller must NOT do is
render it again: the single definition above would then have two call
sites per failure, and the operator would read the same diagnostic
twice.
"""

from __future__ import annotations

import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.
from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.config import (  # noqa: E402
    Config,
    ConfigParseError,
    load_config,
    resolve_check_universe,
)

__all__: list[str] = [
    "CONFIG_PARSE_FAILED_EVENT",
    "load_config_or_report",
    "resolve_check_context_or_report",
]


# Byte-identical to the wording `required_role_keys_declared` has emitted
# since the rejecting loader landed. Consumers grep their check output, so
# changing it here would silently retire a string other people's tooling
# already matches on.
CONFIG_PARSE_FAILED_EVENT = "consumer config parse failed"


def _report_parse_failure(
    *, log: structlog.stdlib.BoundLogger, check_id: str, exc: ConfigParseError
) -> None:
    """Emit the ONE structured event both entry points render.

    Private and shared rather than duplicated per entry point: the whole
    reason this module exists is that the diagnostic has a single
    definition, so two copies of it here would reintroduce inside the
    helper exactly the drift the helper removes from its call sites.
    """
    log.exception(
        CONFIG_PARSE_FAILED_EVENT,
        check_id=check_id,
        status="fail",
        error=str(exc),
    )


def load_config_or_report(
    *, repo_root: Path, log: structlog.stdlib.BoundLogger, check_id: str
) -> IOResult[Config, ConfigParseError]:
    """Load the consumer config, or render the parse failure onto the failure track.

    Returns `IOSuccess(config)` on success. On `ConfigParseError` it emits
    exactly ONE structured `log.exception` carrying `check_id`,
    `status="fail"` and `error`, and returns `IOFailure(exc)` — the
    caller's cue to exit non-zero, carrying the error it exits over. It
    NEVER re-raises and never propagates: a supervisor that let the
    exception through would put the interpreter's traceback back on
    stderr, which is the failure mode this helper exists to remove.

    The catch is NARROW by design and stays narrow. `ConfigParseError` is
    the loader's declared IO-layer failure; widening this to `Exception`
    would swallow bugs in the check itself and would convict this module
    under `no_except_outside_io`, which permits a broad catch only as a
    marked, sole boundary catch inside a declared supervisor entry file.
    """
    try:
        return IOSuccess(load_config(repo_root=repo_root))
    except ConfigParseError as exc:
        _report_parse_failure(log=log, check_id=check_id, exc=exc)
        return IOFailure(exc)


def resolve_check_context_or_report(
    *, log: structlog.stdlib.BoundLogger, check_id: str
) -> IOResult[tuple[Path, tuple[Path, ...], Config], ConfigParseError]:
    """Resolve `(repo_root, universe, config)`, or render the parse failure.

    The entry point for the applies-to-all checks — the ones that open
    `main()` with `resolve_check_universe()`. They reach the consumer
    config TWICE, and the FIRST reach is not their own:
    `config.iter_first_party_py_files` calls `load_config` itself to get
    the `tests_tree_prefix` it filters the git-derived walk with, so a
    malformed `pyproject.toml` raises inside `resolve_check_universe()` —
    before the check's own `load_config` line is ever evaluated. Wrapping
    only that later line would leave the traceback exactly where it was
    and render nothing, so those callers need THIS entry point rather
    than `load_config_or_report`. Measured 2026-09-08 on `no_inheritance`:
    the escaping traceback's innermost check frame was
    `root, universe = resolve_check_universe()`, not the `load_config`
    line below it.

    The trailing `load_config` is deliberately UNGUARDED. The resolution
    above it has already parsed the same file successfully, so this call
    re-reads a config that is known to parse; a second guard here would
    add a branch no test could reach under this repo's 100% gate.

    ONLY `ConfigParseError` is caught. `resolve_check_universe` also
    raises `GitToplevelError` and `GitLsFilesError`, and those keep
    propagating on purpose: they say the check is running outside a git
    working tree, which is a caller defect rather than a consumer's
    malformed config, and rendering them as a config diagnostic would
    misname the failure.
    """
    try:
        root, universe = resolve_check_universe()
    except ConfigParseError as exc:
        _report_parse_failure(log=log, check_id=check_id, exc=exc)
        return IOFailure(exc)
    return IOSuccess((root, universe, load_config(repo_root=root)))

"""factory_provenance_gate — the hermetic factory-provenance commit gate.

The decision half of the commit-time provenance gate whose refuse branch
lives in `install_commit_refuse_hooks.CANONICAL_HOOK_BODY`. The hook body
reads the `livespec.factoryRunId` git config marker and hands this module
the commit-message file plus whatever it read; this module classifies the
staged tree, resolves the host-wide mode, writes the provenance trailer,
and returns the verdict.

WHAT IT DECIDES, and what it deliberately does not: the gate decides WHO
may commit product implementation `.py` — a factory run, or a human who
declared an audited exception. Whether that commit is test-driven is the
Red-Green-Replay gate's question, and the two are AND-ed without either
touching the other.

SCOPE is the SAME universe Red-Green-Replay classifies: a staged,
non-deleted `.py` path under one of `config.derive_source_prefixes` and
not `config.is_vendored_path`. Both shared predicates are imported rather
than restated, because two implementations of one rule is exactly the
drift that promotion into `config` exists to prevent.

MODE IS HOST-WIDE AND DEFAULTS TO WARN. The mode file lives at
`${XDG_CONFIG_HOME:-$HOME/.config}/livespec/factory-provenance-mode`,
OUTSIDE every repository, so no checkout can arm — or disarm — the gate
that judges its own commits. Only the exact token `fail` arms it; an
absent, unreadable, or unrecognized file resolves to `warn`, which emits
the record and lets the commit through. The flip to `fail` is a separate,
coordinated rollout (work-item livespec-dev-tooling-xzxrm5), so during
the warn phase this module's job is to MEASURE, not to block.

THE AUDITED EXCEPTION is a non-empty `Factory-Override: <reason>` trailer
in the commit message. It is recorded at warning level AND it is durable
in the commit itself — the message carries the reason forever, which is
what makes it auditable rather than merely permissive. An empty
`Factory-Override:` is not an exception: a reason is the whole of what is
being audited.

CLI:
    python -m livespec_dev_tooling.factory_provenance_gate \
        <commit-message-file> [<factory-run-id>]

Exit codes:
- `0` — proceed. The marker was present (and the trailer written), or no
  product `.py` is staged, or an audited exception was declared, or the
  mode is `warn`.
- `9` — REFUSE. Product `.py` is staged with no marker and no audited
  exception, and the host-wide mode is `fail`. The code is deliberately
  NOT `1`: the hook body refuses on this code ALONE, so an absent
  interpreter, an unresolvable module, or any crash (all of which exit
  something else) fails OPEN rather than turning a gate defect into a
  fleet-wide commit outage.

Output discipline: structlog JSON to stderr; no `print`, no
`sys.stdout.write` / `sys.stderr.write`.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.config import (  # noqa: E402
    ConfigParseError,
    derive_source_prefixes,
    is_vendored_path,
    load_config,
)

__all__: list[str] = [
    "MODE_FILE_RELATIVE_PATH",
    "REFUSE_EXIT_CODE",
    "gate",
    "main",
]


# The one exit code the hook body's refuse branch acts on. See the module
# docstring for why it is not `1`.
REFUSE_EXIT_CODE = 9

# The host-wide mode file, relative to `${XDG_CONFIG_HOME:-$HOME/.config}`.
MODE_FILE_RELATIVE_PATH = Path("livespec") / "factory-provenance-mode"

_FAIL_MODE = "fail"
_WARN_MODE = "warn"
_RUN_ID_TRAILER_KEY = "Factory-Run-Id"

# Anchored at line start so a commented-out `# Factory-Override: …` in the
# message template is NOT an exception, and requiring a non-space first
# character so a bare `Factory-Override:` declares nothing.
_OVERRIDE_TRAILER_RE = re.compile(r"^Factory-Override:[ \t]*(\S.*?)[ \t]*$", re.MULTILINE)


def _configure_logger() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger("factory_provenance_gate")


def _staged_paths(*, cwd: Path) -> list[str]:
    """Return staged paths, EXCLUDING deletions (`--diff-filter=d`).

    The same listing Red-Green-Replay takes, for the same reason: a staged
    deletion carries no content whose provenance could be asserted, so it
    must drop out of classification entirely rather than make a pure
    removal owe a factory run.
    """
    result = subprocess.run(  # noqa: S603
        ["git", "diff", "--cached", "--name-only", "--diff-filter=d"],  # noqa: S607
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    return [line for line in result.stdout.splitlines() if line]


def _staged_product_paths(*, cwd: Path) -> tuple[str, ...]:
    """Return the staged PRODUCT implementation `.py` paths, in staged order.

    A malformed `[tool.livespec_dev_tooling]` block resolves to "nothing
    in scope" rather than to a traceback: this runs inside a git hook on
    every commit, and a config defect is the repo's own problem to fix at
    its own gate — it must not also become an unexplained commit failure
    here.
    """
    try:
        prefixes = derive_source_prefixes(config=load_config(repo_root=cwd))
    except ConfigParseError:
        return ()
    return tuple(
        path
        for path in _staged_paths(cwd=cwd)
        if path.endswith(".py")
        and path.startswith(prefixes)
        and not is_vendored_path(rel_path=Path(path))
    )


def _mode_file_path(*, env: Mapping[str, str]) -> Path:
    """Resolve the host-wide mode file from the environment's XDG base."""
    configured = env.get("XDG_CONFIG_HOME", "")
    base = Path(configured) if configured else Path(env.get("HOME", "")) / ".config"
    return base / MODE_FILE_RELATIVE_PATH


def _resolve_mode(*, env: Mapping[str, str]) -> str:
    """Return `fail` only for the exact armed token; everything else is `warn`.

    Absent, unreadable, and unrecognized all resolve to `warn` — the
    direction that lets commits through. A gate mid-rollout that cannot
    read its own mode must not start refusing on the strength of a typo.
    """
    try:
        raw = _mode_file_path(env=env).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return _WARN_MODE
    return _FAIL_MODE if raw.strip().lower() == _FAIL_MODE else _WARN_MODE


def _message_text(*, message_path: Path) -> str:
    """Return the commit message, or `""` when it cannot be read as text."""
    try:
        return message_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _override_reason(*, message: str) -> str:
    """Return the LAST non-empty `Factory-Override:` reason, or `""`.

    Last rather than first: an amended message may carry an earlier
    reason above the one the author just wrote, and the current one is
    what the exception is being claimed under.
    """
    reasons = _OVERRIDE_TRAILER_RE.findall(message)
    return reasons[-1] if reasons else ""


def _write_run_id_trailer(*, message_path: Path, factory_run_id: str) -> None:
    """Record the run id as a `Factory-Run-Id:` trailer on the commit message.

    `--if-exists replace` keeps a Red→Green amend from accumulating one
    trailer per attempt. It is safe HERE — unlike for the `TDD-Red-*`
    schema, where git's prefix-aliasing silently drops the longer-keyed
    trailer — because no other trailer key this fleet writes is a prefix
    of `Factory-Run-Id` or has it as one.

    Failure is not raised: `check=False` and the returncode is ignored on
    purpose, so a git that cannot rewrite the message loses the trailer
    rather than the commit.
    """
    _ = subprocess.run(  # noqa: S603
        [  # noqa: S607
            "git",
            "interpret-trailers",
            "--in-place",
            "--if-exists",
            "replace",
            "--trailer",
            f"{_RUN_ID_TRAILER_KEY}: {factory_run_id}",
            str(message_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def gate(
    *,
    cwd: Path,
    message_path: Path,
    factory_run_id: str,
    env: Mapping[str, str],
    log: structlog.stdlib.BoundLogger,
) -> int:
    """Decide the commit's provenance verdict; see the module docstring for the codes.

    The marker is read FIRST and short-circuits everything below it: a
    commit made under a factory run is in provenance by construction, so
    it neither needs the staged-tree classification nor an exception.
    """
    if factory_run_id:
        _write_run_id_trailer(message_path=message_path, factory_run_id=factory_run_id)
        log.info(
            "factory provenance recorded",
            factory_run_id=factory_run_id,
            trailer=_RUN_ID_TRAILER_KEY,
        )
        return 0
    product_paths = _staged_product_paths(cwd=cwd)
    if not product_paths:
        return 0
    reason = _override_reason(message=_message_text(message_path=message_path))
    if reason:
        log.warning(
            "factory provenance AUDITED EXCEPTION: Factory-Override declared",
            reason=reason,
            staged_product_paths=list(product_paths),
        )
        return 0
    mode = _resolve_mode(env=env)
    log.warning(
        "product .py committed without factory provenance",
        mode=mode,
        staged_product_paths=list(product_paths),
        marker="livespec.factoryRunId",
        mode_file=str(_mode_file_path(env=env)),
    )
    return REFUSE_EXIT_CODE if mode == _FAIL_MODE else 0


def main() -> int:
    log = _configure_logger()
    parser = argparse.ArgumentParser(
        description="Decide the factory-provenance verdict for a staged commit.",
    )
    _ = parser.add_argument(
        "message_file",
        help="Path to the commit-message file (the commit-msg hook's argv[1]).",
    )
    _ = parser.add_argument(
        "factory_run_id",
        nargs="?",
        default="",
        help="The livespec.factoryRunId marker the hook read, or empty when unset.",
    )
    parsed = parser.parse_args()
    return gate(
        cwd=Path.cwd(),
        message_path=Path(str(parsed.message_file)),
        factory_run_id=str(parsed.factory_run_id).strip(),
        env=os.environ,
        log=log,
    )


if __name__ == "__main__":
    raise SystemExit(main())

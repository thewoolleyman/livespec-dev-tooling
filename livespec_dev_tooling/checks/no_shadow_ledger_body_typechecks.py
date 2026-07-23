"""no_shadow_ledger_body_typechecks — the canonical no-shadow-ledger body stays strict-clean.

The neutral no-shadow-ledger Stop-hook body ships as the wheel-safe string
constant `livespec_dev_tooling.install_no_shadow_ledger.
CANONICAL_NO_SHADOW_LEDGER_BODY` (NOT a real `.py` module) so it travels in
the wheel exactly as `install_commit_refuse_hooks`'s `CANONICAL_HOOK_BODY`
does. Because it is a carrier string, its logic is executed and covered ONLY
where it is INSTALLED — in the two Driver repos (livespec-driver-claude at
`.claude-plugin/hooks/`, livespec-driver-codex at `livespec/hooks/`) — never
here. Promoting it to a real module would pull it into this repo's
`fail_under = 100` coverage universe and force a coverage `omit` exemption;
keeping it a string keeps the carrier out of that universe.

The carrier's cost is that pyright never sees it: an annotation regression in
the body would ship silently. This check closes that gap. It renders the
constant to a throwaway `.py` and runs pyright in strict mode against it,
failing when pyright reports any error, so the body cannot drift off
strict-clean even though it is never imported or executed in this repo.

Strict parity: the rendered body is checked under a `pyrightconfig.json`
mirroring this repo's `[tool.pyright]` strict bar — `typeCheckingMode =
"strict"` plus the strict-plus diagnostics the repo elevates to errors
(notably `reportUnusedCallResult`, which catches an unbound
`sys.stdout.write(...)` result, and `reportUnnecessaryCast`) and the two it
deliberately relaxes (so an intentional multi-line message assembly is not
falsely flagged). The settings are held here as a module constant rather than
read from `pyproject.toml`: this check ships in the wheel and must apply the
SAME strict bar to the packaged constant wherever it runs, and a wheel install
carries no repo `pyproject.toml` to read. The pass/fail verdict is pyright's
EXIT CODE (0 = clean, non-zero = diagnostics) — the exact gate `uv run pyright`
applies, and robust to a freshly-bootstrapped pyright printing platform-detection
noise to stdout ahead of its JSON. The JSON is parsed only best-effort, to name
the failing lines/rules in the structured error.

Exit codes:
- `0` — the rendered body is pyright-strict clean (pyright reports no
  error-severity diagnostics), OR pyright is unavailable in this environment
  (graceful skip; the invariant is enforced in this repo's own aggregate / CI
  where pyright is a pinned dev dependency).
- `4` — pyright reported one or more error-severity diagnostics against the
  rendered body: the canonical body drifted off strict-clean. The structured
  error names each failing line and rule. Corrective action: fix the flagged
  annotations/bindings in `CANONICAL_NO_SHADOW_LEDGER_BODY`.

Output discipline: structlog JSON to stderr; no `print`, no
`sys.stdout.write` / `sys.stderr.write`.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

# The canonical body is the SINGLE source of truth, shipped as a module
# constant in the installer so it travels in the wheel. The check imports it
# (rather than carrying a second copy) so the exact bytes the installer writes
# are what get type-checked — there is no drift seam.
from livespec_dev_tooling.install_no_shadow_ledger import (  # noqa: E402
    CANONICAL_NO_SHADOW_LEDGER_BODY,
)

__all__: list[str] = []


_CHECK_ID = "no_shadow_ledger_body_typechecks"
_FAIL_EXIT = 4
_RENDERED_BODY_FILENAME = "no_shadow_ledger_body.py"

# A minimal pyright config mirroring this repo's `[tool.pyright]` strict bar
# (see the module docstring for why it is held here rather than read from
# `pyproject.toml`). Kept in lockstep with `[tool.pyright]` by review.
_PYRIGHT_STRICT_CONFIG: dict[str, object] = {
    "typeCheckingMode": "strict",
    "pythonVersion": "3.10",
    "reportUnusedCallResult": "error",
    "reportImplicitOverride": "error",
    "reportUninitializedInstanceVariable": "error",
    "reportUnnecessaryTypeIgnoreComment": "error",
    "reportUnnecessaryCast": "error",
    "reportUnnecessaryIsInstance": "error",
    "reportImplicitStringConcatenation": "warning",
    "reportPrivateUsage": "none",
}

_REMEDY = (
    "fix the flagged annotations/bindings in "
    "`livespec_dev_tooling.install_no_shadow_ledger."
    "CANONICAL_NO_SHADOW_LEDGER_BODY` so it is pyright-strict clean"
)


def _configure_logger() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger(_CHECK_ID)


def _pyright_available() -> bool:
    """True when the pinned `pyright` package is importable in this interpreter."""
    return importlib.util.find_spec("pyright") is not None


def _run_pyright_strict(*, body: str) -> tuple[int, str]:
    """Render `body` + the strict config to a throwaway dir, run pyright, return (rc, stdout).

    The rendered body plus a `pyrightconfig.json` (the strict-parity config,
    scoped to the rendered file only) are written into a `TemporaryDirectory`;
    `python -m pyright --outputjson` runs with that directory as cwd so pyright
    inspects ONLY the rendered body. Returns pyright's exit code (the verdict)
    and its raw `--outputjson` stdout (the best-effort detail source).
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        _ = (tmp_dir / _RENDERED_BODY_FILENAME).write_text(body, encoding="utf-8")
        config = dict(_PYRIGHT_STRICT_CONFIG)
        config["include"] = [_RENDERED_BODY_FILENAME]
        _ = (tmp_dir / "pyrightconfig.json").write_text(json.dumps(config), encoding="utf-8")
        # S603/S607: argv is a fixed list (this interpreter + literal `-m
        # pyright` flags); no shell, no caller-supplied input.
        completed = subprocess.run(
            [sys.executable, "-m", "pyright", "--outputjson"],
            cwd=str(tmp_dir),
            capture_output=True,
            text=True,
            check=False,
        )
    return completed.returncode, completed.stdout


def _locate_pyright_json(*, stdout: str) -> dict[str, object] | None:
    """Best-effort: parse pyright's JSON object out of `stdout`, tolerating leading noise.

    A freshly-bootstrapped pyright can print platform-detection lines to stdout
    BEFORE its JSON, so `json.loads` on the whole payload would choke. Retry from
    each line that opens a brace, returning the first suffix that parses. Returns
    None when no candidate parses — the caller then falls back to the raw output.
    """
    offset = 0
    for line in stdout.splitlines(keepends=True):
        stripped = line.lstrip()
        if stripped.startswith("{"):
            try:
                parsed = json.loads(stdout[offset + len(line) - len(stripped) :])
            except (ValueError, json.JSONDecodeError):
                parsed = None
            if parsed is not None:
                return cast("dict[str, object]", parsed)
        offset += len(line)
    return None


def _one_based_line(*, diagnostic: dict[str, object]) -> int:
    """The 1-based start line of a diagnostic, or 0 when the range is absent/malformed."""
    range_obj = diagnostic.get("range")
    if not isinstance(range_obj, dict):
        return 0
    start = cast("dict[str, object]", range_obj).get("start")
    if not isinstance(start, dict):
        return 0
    line = cast("dict[str, object]", start).get("line")
    if not isinstance(line, int):
        return 0
    return line + 1


def _summary_line(*, diagnostic: dict[str, object]) -> str:
    """A compact `L<line> <rule>: <first message line>` summary of one diagnostic."""
    rule = diagnostic.get("rule")
    rule_text = rule if isinstance(rule, str) else "(no-rule)"
    message = diagnostic.get("message")
    first_message_line = message.splitlines()[0] if isinstance(message, str) else ""
    return f"L{_one_based_line(diagnostic=diagnostic)} {rule_text}: {first_message_line}"


def _diagnostic_detail(*, stdout: str) -> list[str]:
    """Human-readable detail for a failing pyright run.

    Locates pyright's JSON object within `stdout` and summarizes its diagnostics;
    falls back to the raw non-empty output lines when the JSON cannot be located
    or carries no diagnostic entries, so a failure is always actionable even when
    pyright's stdout is shaped unexpectedly.
    """
    parsed = _locate_pyright_json(stdout=stdout)
    if parsed is not None:
        diagnostics = parsed.get("generalDiagnostics")
        if isinstance(diagnostics, list):
            summaries = [
                _summary_line(diagnostic=cast("dict[str, object]", entry))
                for entry in cast("list[object]", diagnostics)
                if isinstance(entry, dict)
            ]
            if summaries:
                return summaries
    return [line for line in stdout.splitlines() if line.strip()]


def _typecheck_body(*, body: str, log: structlog.stdlib.BoundLogger) -> int:
    """Type-check `body` under the strict config; 4 when pyright reports diagnostics, else 0.

    The pass/fail verdict is pyright's EXIT CODE (0 = clean, non-zero = one or
    more diagnostics), which is robust to a freshly-bootstrapped pyright printing
    platform-detection noise to stdout ahead of its JSON. The JSON is parsed only
    best-effort, to name the failing lines/rules in the structured error.

    Skips (exit 0) when pyright is unavailable — the invariant is still enforced
    wherever pyright is present (this repo's aggregate / CI).
    """
    if not _pyright_available():
        log.warning(
            "no_shadow_ledger_body_typechecks: pyright unavailable — check skips",
            check_id=_CHECK_ID,
            level="info",
            hint="install the pinned `pyright` dev dependency to enforce this check",
        )
        return 0
    returncode, stdout = _run_pyright_strict(body=body)
    if returncode == 0:
        return 0
    log.error(
        "no_shadow_ledger_body_typechecks: canonical body is not pyright-strict clean",
        check_id=_CHECK_ID,
        status="fail",
        pyright_returncode=returncode,
        diagnostics=_diagnostic_detail(stdout=stdout),
        hint=_REMEDY,
    )
    return _FAIL_EXIT


def main() -> int:
    log = _configure_logger()
    return _typecheck_body(body=CANONICAL_NO_SHADOW_LEDGER_BODY, log=log)


if __name__ == "__main__":
    raise SystemExit(main())

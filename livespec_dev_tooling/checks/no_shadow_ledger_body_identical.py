"""no_shadow_ledger_body_identical — verify the neutral no-shadow-ledger hook body.

Per Conformance-Pattern concern #1's byte-identity precedent (mirrored from
`primary_checkout_commit_refuse_hook_installed`), a consumer that declares
the `neutral_hook_body_path` role key (a `[tool.livespec_dev_tooling]` key
in its `pyproject.toml`) MUST keep the file at that path BYTE-IDENTICAL to
the single packaged carrier constant
`livespec_dev_tooling.install_no_shadow_ledger.CANONICAL_NO_SHADOW_LEDGER_BODY`
(imported here — this module is NOT a second copy of the body). The neutral
body is the Stop-hook that BOTH livespec Driver plugins ship
(livespec-driver-claude at `.claude-plugin/hooks/`, livespec-driver-codex at
`livespec/hooks/`), so this check guards each Driver's copy against drift
from the single dev-tooling-packaged source.

Unlike the commit-refuse hook (mandatory at every primary checkout), this
role key is OPT-IN: a consumer that has not declared
`neutral_hook_body_path` is not a Driver repo (or has not yet wired the
role key), so the check no-ops rather than failing.

Exit codes:
- `0` — the role key is absent (no-op — this consumer does not carry the
  neutral hook body), or the configured path exists and is byte-identical
  to the canonical body.
- `4` — fail. The configured path is missing (or not a regular file), or
  its bytes differ from the canonical body. Corrective action: run
  `just install-no-shadow-ledger` (the from-package installer that is the
  single source of the body).

Output discipline: structlog JSON to stderr; no `print`, no
`sys.stdout.write` / `sys.stderr.write`.
"""

from __future__ import annotations

import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.config import load_config  # noqa: E402

# The canonical body is the SINGLE source of truth, shipped as a module
# constant in the installer so it travels in the wheel. The check imports
# it (rather than carrying a second copy) so byte-identity is verified
# against the exact bytes the installer writes — there is no drift seam.
from livespec_dev_tooling.install_no_shadow_ledger import (  # noqa: E402
    CANONICAL_NO_SHADOW_LEDGER_BODY,
)

__all__: list[str] = []


_CHECK_ID = "no_shadow_ledger_body_identical"
_FAIL_EXIT = 4

_MISSING_FAILURE_MODE = "missing"
_BODY_MISMATCH_FAILURE_MODE = "body_mismatch"
_REMEDY = (
    "run `just install-no-shadow-ledger` (the from-package installer that "
    "writes the single canonical neutral no-shadow-ledger hook body "
    "byte-for-byte to the configured `neutral_hook_body_path`)"
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


def main() -> int:
    log = _configure_logger()
    config = load_config(repo_root=Path.cwd())
    if config.neutral_hook_body_path is None:
        log.info(
            "role key absent — check no-ops",
            check_id=_CHECK_ID,
            role="neutral_hook_body_path",
            level="info",
        )
        return 0
    path = Path.cwd() / config.neutral_hook_body_path
    if not path.is_file():
        log.error(
            "no_shadow_ledger_body_identical: hook body missing",
            check_id=_CHECK_ID,
            status="fail",
            failure_mode=_MISSING_FAILURE_MODE,
            path=str(path),
            hint=_REMEDY,
        )
        return _FAIL_EXIT
    if path.read_text(encoding="utf-8") != CANONICAL_NO_SHADOW_LEDGER_BODY:
        log.error(
            "no_shadow_ledger_body_identical: hook body drifted from canonical",
            check_id=_CHECK_ID,
            status="fail",
            failure_mode=_BODY_MISMATCH_FAILURE_MODE,
            path=str(path),
            hint=_REMEDY,
        )
        return _FAIL_EXIT
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

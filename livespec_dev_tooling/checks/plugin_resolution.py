"""plugin_resolution — cross-harness plugin-resolution Verifier (Conformance concern #2).

The Verifier slot of the Conformance Pattern's Cross-harness plugin-resolution
concern (concern #2), per `livespec/SPECIFICATION/non-functional-requirements.md`
§"Conformance Pattern". The Contract: a governed repo's documented
command/skill surface MUST resolve *and run* from a fresh session of each
*declared* harness; the Verifier "invokes a canonical command and asserts it
resolves and returns, per declared harness, and rejects a raw-CLI fallback as
proof of resolution. Exemption: an unsupported harness declared explicitly."

This catches the ob-4ts breakage class: a plugin adoption shipped "done" while
the `/livespec:*` slash commands did not resolve, because the acceptance
tolerated a raw `bd` fallback. A fail-closed Verifier here makes that
un-shippable — it ONLY ever invokes the slash-/name-selected command surface
and NEVER substitutes a raw-CLI success for a command-surface success.

The check reads the optional `harnesses` declaration from the repo's local
`.livespec.jsonc` (a project-config concern, sibling to `template` /
`spec_root` / `implementation` — NOT the source-tree-layout schema of
`pyproject.toml` `[tool.livespec_dev_tooling]`, which §"Schema location"
confines to layout role keys). The declaration is an object keyed by harness
name:

    "harnesses": {
      "codex":  { "status": "supported", "canonical_command": "livespec:next" },
      "claude": { "status": "exempt", "reason": "<why unsupported here>" }
    }

Two layers:

- **Always-on declaration-integrity gate** (every `just check`, deterministic,
  no subprocess): parse `harnesses`. Absent → SKIP (exit 0); present → validate
  fail-closed (known harness keys; `status` ∈ {supported, exempt}; `exempt`
  carries a `reason`; `supported` carries a `canonical_command`). A
  malformed/unknown/garbled declaration → FAIL (exit 4). This makes the check
  meaningfully always-invoked per the "carve-outs are a severity lever; always
  wired + always invoked" discipline.
- **Live resolution smoke** (opt-in, env-gated by the SAME `LIVESPEC_E2E_HARNESS`
  dialect the cli_e2e harness uses — `real` runs it, default `mock` does NOT):
  each `supported` harness is routed to ITS OWN runner (`_build_live_runners`) so
  a codex command is never issued through the claude binary. `claude` runs the
  genuine cli_e2e smoke (issue the `/`-prefixed slash command through the
  `CliRunner` seam, whose `RealCliRunner` shells `claude`); `codex` delegates to
  its repo-local smoke (`check-codex-skill-picker`) via a `DelegatedResolutionRunner`
  → SKIP, rather than mis-routing. The decision per harness, folding in work-item
  livespec-mjnv's skip-vs-fail distinction:
    - `exempt` → PASS (the declared Exemption slot — no smoke run).
    - `supported` but delegated to a repo-local smoke (codex) → SKIP (the genuine
      live proof is the delegated check, not this layer).
    - `supported` + binary unavailable → SKIP, NOT fail (mjnv: "can't run here"
      ≠ "command failed"; the smoke runs where the binary is present, e.g. CI).
    - `supported` + available + resolves and returns (exit 0) → PASS.
    - `supported` + available + the command does NOT resolve (or only a raw-CLI
      fallback would succeed) → FAIL (the ob-4ts class).

All real-subprocess code lives behind the injectable `CliRunner` seam, so tests
inject a deterministic fake and never spawn a process.

Exit codes:
- `0` — pass, or skipped (no `harnesses` declaration; unreadable `.livespec.jsonc`;
  live layer gated off in `mock`; per-harness binary unavailable / exempt).
- `4` — fail (a malformed `harnesses` declaration, OR a `supported` harness whose
  canonical command did not resolve in the live layer).

Output discipline: structlog JSON to stderr; no `print`, no `sys.stderr.write`.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import jsoncomment  # noqa: E402  — vendor-path-aware import after sys.path insert.
import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.testing.cli_e2e import (  # noqa: E402  — package import after sys.path insert.
    CliRunner,
    select_runner,
)

__all__: list[str] = []


_CHECK_ID = "plugin_resolution"
_FAIL_EXIT = 4

_LIVESPEC_JSONC = ".livespec.jsonc"
_HARNESSES_KEY = "harnesses"

# The known agent-runtime harnesses a governed repo MAY declare. An unknown key
# is a garbled declaration (fail-closed) rather than a silently-ignored entry.
_KNOWN_HARNESSES = frozenset({"claude", "codex"})

_STATUS_SUPPORTED = "supported"
_STATUS_EXEMPT = "exempt"

# The cli_e2e fleet selector dialect, reused verbatim (NOT a new env var):
# `real` runs the live resolution smoke; `mock` (the default `just check` value)
# runs only the always-on declaration-integrity gate.
_HARNESS_SELECTOR_ENV = "LIVESPEC_E2E_HARNESS"
_HARNESS_REAL = "real"
_HARNESS_MOCK = "mock"

# load_harnesses outcome states.
_LOAD_SKIP = "skip"
_LOAD_ABSENT = "absent"
_LOAD_MALFORMED = "malformed"
_LOAD_OK = "ok"

# Per-harness live-layer decisions.
_DECISION_PASS = "pass"
_DECISION_SKIP = "skip"
_DECISION_FAIL = "fail"


@dataclass(frozen=True, kw_only=True)
class HarnessDecl:
    """One well-formed `harnesses` entry — a harness name and its declared status.

    `canonical_command` is non-empty for a `supported` harness (the command the
    live smoke issues); `reason` is non-empty for an `exempt` harness (the
    declared opt-out justification). The unused field stays the empty string.
    """

    harness: str
    status: str
    reason: str = ""
    canonical_command: str = ""


@dataclass(frozen=True, kw_only=True)
class HarnessLoad:
    """Outcome of reading the `harnesses` declaration from `.livespec.jsonc`.

    `state` is one of `_LOAD_SKIP` (no/unreadable `.livespec.jsonc` — a no-op
    for a non-governed dir), `_LOAD_ABSENT` (a `.livespec.jsonc` exists but
    declares no `harnesses` — fail-closed; required fleet-wide since M6),
    `_LOAD_MALFORMED` (declaration present but garbled — fail-closed), or
    `_LOAD_OK` (well-formed `declarations`). `detail` carries the human-readable
    reason for diagnostics.
    """

    state: str
    declarations: tuple[HarnessDecl, ...] = ()
    detail: str = ""


@dataclass(frozen=True, kw_only=True)
class ResolutionOutcome:
    """Facts a resolution runner reports for one supported harness.

    `available` is whether the harness binary is present in this environment;
    `resolved` is whether the canonical command resolved AND returned exit 0
    through the command surface (never via a raw-CLI substitute).
    """

    available: bool
    resolved: bool


class ResolutionRunner(Protocol):
    """Injectable per-harness resolution seam.

    `resolve` issues a harness's canonical command through its command surface
    ONLY (a slash command on claude, a name-selected command on codex) and
    reports the facts the decision logic consumes — it NEVER invokes a raw CLI.
    `CliResolutionRunner` is the production implementation; a test injects a
    deterministic fake so no subprocess is spawned.
    """

    def resolve(self, *, harness: str, canonical_command: str) -> ResolutionOutcome: ...


def _command_surface_prompt(*, harness: str, canonical_command: str) -> str:
    """Render the canonical command as the harness's command-surface invocation.

    codex name-selects the command verbatim (`livespec:next`); every other
    harness (claude today) issues it as a `/`-prefixed slash command
    (`/livespec:next`). This is the ONLY form the Verifier ever issues — a raw
    CLI (`bd …`) is never substituted.
    """
    if harness == "codex":
        return canonical_command
    return "/" + canonical_command


@dataclass(frozen=True, kw_only=True)
class CliResolutionRunner:
    """Production `ResolutionRunner` backed by the cli_e2e `CliRunner` seam.

    Availability is `shutil.which(<harness>)`; the canonical command is issued
    as the harness's command-surface invocation through the injected
    `cli_runner`. This is the single place real-subprocess code can run (inside
    `CliRunner.run`); a test injects a fake `cli_runner` plus a stubbed
    `shutil.which`, so the runner is fully exercised without spawning.
    """

    cli_runner: CliRunner

    def resolve(self, *, harness: str, canonical_command: str) -> ResolutionOutcome:
        if shutil.which(harness) is None:
            return ResolutionOutcome(available=False, resolved=False)
        result = self.cli_runner.run(
            prompt=_command_surface_prompt(harness=harness, canonical_command=canonical_command),
            home=Path.home(),
            cwd=Path.cwd(),
            resume_session_id=None,
        )
        return ResolutionOutcome(available=True, resolved=result.exit_code == 0)


@dataclass(frozen=True, kw_only=True)
class DelegatedResolutionRunner:
    """A `ResolutionRunner` for a harness whose genuine live smoke is repo-local.

    Some harnesses' resolve-and-run proof lives in the harness's OWN repo — codex's
    is the repo-local `check-codex-skill-picker` PTY smoke — not this dev-tooling
    cross-harness live layer, whose `CliResolutionRunner` shells the `claude` binary.
    Routing such a harness here returns an unavailable outcome (→ SKIP) so the
    dev-tooling check NEVER mis-routes the canonical command through a DIFFERENT
    harness's binary (e.g. `claude -p "livespec:next"` for a codex command); the
    genuine live proof is the delegated repo-local check. `reason` is the
    human-readable delegation note for diagnostics.
    """

    reason: str

    def resolve(self, *, harness: str, canonical_command: str) -> ResolutionOutcome:
        _ = (harness, canonical_command)
        return ResolutionOutcome(available=False, resolved=False)


# codex's genuine live resolution smoke is the repo-local check-codex-skill-picker
# PTY check, not this cross-harness live layer; delegate it so the dev-tooling check
# never routes a codex command through the claude binary.
_CODEX_DELEGATION_REASON = (
    "codex live resolution is verified by the repo-local codex resolution check "
    "(check-codex-skill-picker), not the dev-tooling cross-harness live layer"
)


def _build_live_runners(*, claude_runner: CliRunner) -> dict[str, ResolutionRunner]:
    """Map each known harness to its live-resolution runner (per-harness routing).

    `claude` runs the genuine cli_e2e smoke (the injected `claude_runner`); `codex`
    delegates to its repo-local smoke (a `DelegatedResolutionRunner` → SKIP) rather
    than mis-routing through the claude binary. The map covers exactly
    `_KNOWN_HARNESSES`, which the declaration-integrity gate guarantees every
    `supported` declaration is drawn from; adding a harness with a genuine
    dev-tooling live runner is a one-line registry addition.
    """
    return {
        "claude": CliResolutionRunner(cli_runner=claude_runner),
        "codex": DelegatedResolutionRunner(reason=_CODEX_DELEGATION_REASON),
    }


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


def _parse_supported(*, harness: str, entry: dict[str, object]) -> tuple[HarnessDecl | None, str]:
    """Validate a `supported` entry: it MUST carry a non-empty `canonical_command`."""
    command = entry.get("canonical_command")
    if not isinstance(command, str) or not command:
        return None, f"supported harness {harness!r} needs a non-empty `canonical_command`"
    return HarnessDecl(harness=harness, status=_STATUS_SUPPORTED, canonical_command=command), ""


def _parse_exempt(*, harness: str, entry: dict[str, object]) -> tuple[HarnessDecl | None, str]:
    """Validate an `exempt` entry: it MUST carry a non-empty `reason`."""
    reason = entry.get("reason")
    if not isinstance(reason, str) or not reason:
        return None, f"exempt harness {harness!r} needs a non-empty `reason`"
    return HarnessDecl(harness=harness, status=_STATUS_EXEMPT, reason=reason), ""


def _parse_entry(*, harness: str, entry: object) -> tuple[HarnessDecl | None, str]:
    """Validate one `harnesses` entry; return `(decl, "")` or `(None, detail)`.

    Fail-closed: an unknown harness key, a non-object entry, a missing/invalid
    `status`, a `supported` entry with no `canonical_command`, or an `exempt`
    entry with no `reason` each yield a `detail` string (and no decl).
    """
    if harness not in _KNOWN_HARNESSES:
        return None, f"unknown harness {harness!r} (known: {sorted(_KNOWN_HARNESSES)})"
    if not isinstance(entry, dict):
        return None, f"harness {harness!r} entry must be an object"
    entry_dict = cast("dict[str, object]", entry)
    status = entry_dict.get("status")
    if status == _STATUS_SUPPORTED:
        return _parse_supported(harness=harness, entry=entry_dict)
    if status == _STATUS_EXEMPT:
        return _parse_exempt(harness=harness, entry=entry_dict)
    return None, f"harness {harness!r} `status` must be 'supported' or 'exempt'"


def _read_livespec_document(*, root: Path) -> tuple[dict[str, object] | None, str]:
    """Read `<root>/.livespec.jsonc` into a dict; return `(document, "")` or `(None, skip_detail)`.

    The three `None` returns are all SKIP (a no-op): the file is absent, it is
    unreadable JSONC (deferred to the dedicated config-integrity tooling), or
    its top-level document is not an object.
    """
    path = root / _LIVESPEC_JSONC
    if not path.is_file():
        return None, "no .livespec.jsonc; no declared harness surface"
    try:
        parsed = jsoncomment.loads(path.read_text(encoding="utf-8"))
    except (ValueError, json.JSONDecodeError):
        return None, "unreadable .livespec.jsonc; deferring to config-integrity tooling"
    if not isinstance(parsed, dict):
        return None, ".livespec.jsonc is not an object"
    return cast("dict[str, object]", parsed), ""


def load_harnesses(*, root: Path) -> HarnessLoad:
    """Read the `harnesses` declaration from `<root>/.livespec.jsonc`.

    Returns a `HarnessLoad`. SKIP states (a no-op for a non-governed dir): the
    file is absent, the file is unreadable JSONC, or the top-level document is
    not an object. A `.livespec.jsonc` that exists but declares no `harnesses`
    key is ABSENT (fail-closed; required fleet-wide since M6). A
    present-but-garbled `harnesses` block is MALFORMED (fail-closed); a
    well-formed block is OK with parsed `declarations`.
    """
    document, skip_detail = _read_livespec_document(root=root)
    if document is None:
        return HarnessLoad(state=_LOAD_SKIP, detail=skip_detail)
    if _HARNESSES_KEY not in document:
        return HarnessLoad(
            state=_LOAD_ABSENT,
            detail="no `harnesses` declaration (required fleet-wide since M6; livespec-zs22.7.7)",
        )
    harnesses = document[_HARNESSES_KEY]
    if not isinstance(harnesses, dict):
        return HarnessLoad(state=_LOAD_MALFORMED, detail="`harnesses` must be an object")
    declarations: list[HarnessDecl] = []
    for harness, entry in cast("dict[str, object]", harnesses).items():
        decl, detail = _parse_entry(harness=harness, entry=entry)
        if decl is None:
            return HarnessLoad(state=_LOAD_MALFORMED, detail=detail)
        declarations.append(decl)
    return HarnessLoad(state=_LOAD_OK, declarations=tuple(declarations))


def decide_harness(*, decl: HarnessDecl, runner: ResolutionRunner) -> str:
    """Map one declared harness to a per-harness decision (pass / skip / fail).

    `exempt` → PASS (the declared Exemption slot; no smoke). `supported` runs
    the resolution smoke: unavailable binary → SKIP (mjnv); resolves+returns →
    PASS; unresolved (or only a raw-CLI fallback would succeed) → FAIL (ob-4ts).
    """
    if decl.status == _STATUS_EXEMPT:
        return _DECISION_PASS
    outcome = runner.resolve(harness=decl.harness, canonical_command=decl.canonical_command)
    if not outcome.available:
        return _DECISION_SKIP
    if outcome.resolved:
        return _DECISION_PASS
    return _DECISION_FAIL


def run_live_layer(
    *,
    declarations: tuple[HarnessDecl, ...],
    runners: dict[str, ResolutionRunner],
    log: structlog.stdlib.BoundLogger,
) -> int:
    """Run the per-harness resolution smoke; return `0` (pass/skip/exempt) or `4` (any fail).

    Each declared harness is decided against ITS OWN runner from `runners` (keyed
    by harness name), so a codex declaration resolves through the codex runner,
    never the claude one.
    """
    any_fail = False
    for decl in declarations:
        decision = decide_harness(decl=decl, runner=runners[decl.harness])
        if decision == _DECISION_FAIL:
            any_fail = True
            log.error(
                "plugin-resolution: canonical command did not resolve",
                check_id=_CHECK_ID,
                status="fail",
                harness=decl.harness,
                canonical_command=decl.canonical_command,
                hint=(
                    "the documented command surface MUST resolve and return from a fresh "
                    "session of this declared harness; a raw-CLI fallback is NOT accepted as "
                    "proof. Install + register the plugin for this harness, or declare it "
                    "`status: exempt` with a `reason`"
                ),
                path=_LIVESPEC_JSONC,
                line=0,
            )
        else:
            log.info(
                "plugin-resolution: harness decision",
                check_id=_CHECK_ID,
                harness=decl.harness,
                decision=decision,
            )
    return _FAIL_EXIT if any_fail else 0


def main() -> int:
    log = _configure_logger()
    load = load_harnesses(root=Path.cwd())
    if load.state == _LOAD_SKIP:
        log.info("plugin-resolution: skipped", check_id=_CHECK_ID, reason=load.detail)
        return 0
    if load.state == _LOAD_ABSENT:
        log.error(
            "plugin-resolution: required `harnesses` declaration is absent",
            check_id=_CHECK_ID,
            status="fail",
            failure_mode="absent_declaration",
            detail=load.detail,
            path=_LIVESPEC_JSONC,
            line=0,
            hint=(
                "declare a top-level `harnesses` object in .livespec.jsonc; mark each agent "
                "runtime ('claude'/'codex') `status` 'supported' (with a `canonical_command`) "
                "or 'exempt' (with a `reason`)"
            ),
        )
        return _FAIL_EXIT
    if load.state == _LOAD_MALFORMED:
        log.error(
            "plugin-resolution: malformed `harnesses` declaration",
            check_id=_CHECK_ID,
            status="fail",
            failure_mode="malformed_declaration",
            detail=load.detail,
            path=_LIVESPEC_JSONC,
            line=0,
            hint=(
                "each `harnesses` key MUST be a known harness ('claude'/'codex') whose entry "
                "has `status` 'supported' (with a `canonical_command`) or 'exempt' (with a "
                "`reason`)"
            ),
        )
        return _FAIL_EXIT
    mode = os.environ.get(_HARNESS_SELECTOR_ENV, _HARNESS_MOCK).strip().lower()
    if mode != _HARNESS_REAL:
        log.info(
            "plugin-resolution: declaration well-formed; live layer gated off",
            check_id=_CHECK_ID,
            selector=mode,
            declared=[decl.harness for decl in load.declarations],
        )
        return 0
    runners = _build_live_runners(claude_runner=select_runner(injected_runner=None))
    return run_live_layer(declarations=load.declarations, runners=runners, log=log)


if __name__ == "__main__":
    raise SystemExit(main())

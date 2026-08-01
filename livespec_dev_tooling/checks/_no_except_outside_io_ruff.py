"""Ruff BLE001 backstop probes for no_except_outside_io.

ON THE `IOResult` RAILWAY — `livespec-dev-tooling-8o8e.5`, epic `8o8e`. These
call `subprocess.run` and `Path.read_text` DIRECTLY rather than through an
injected seam, so they are the I/O boundary itself and `IOResult` rather than
`Result` is the honest container (the same direct-call-versus-injected-seam
reading that puts `_origin_remote` on `IOResult` and leaves `fetch_manifest`
on `Result`).

## WHAT THE OLD `list[tuple[Path, str]]` COULD NOT SAY — and `8o8e.5` named only ONE of the four

The filed defect was "an unreadable `pyproject.toml` makes the BLE001 backstop
check report no gaps". Reading the module found FOUR fused outcomes, and the
filed one is the mildest:

1. **`pyproject.toml` unreadable** — `read_text` was UNCAUGHT, so it raised an
   `OSError` out of a function annotated `bool` and out of this module's only
   public function, annotated `list`. That is livespec v179 clause (a).
2. **`ruff` ABSENT FROM PATH** — both `subprocess.run` calls were UNGUARDED, so
   a missing binary raised `FileNotFoundError` from the same annotated-`list`
   function. Not a `None` at all, exactly like `resolve_owner`'s third arm.
3. **`ruff check --show-files` FAILING** — its `returncode` was **NEVER READ**.
   A failed enumeration yields empty stdout, so `ruff_files` is empty, so EVERY
   inspected file is reported as "excluded from Ruff". The check does not go
   quiet — it manufactures a gap for every file in the repo and blames Ruff's
   exclusion rules for a Ruff that never ran.
4. **`ruff check --show-settings` FAILING** — fused with "BLE001 is not
   enabled" by `result.returncode == 0 and _RUFF_BLE001_SETTING in ...`, so a
   broken invocation was reported to the operator as a CONFIGURATION verdict
   about their `select` list.

**AN ABSENT `pyproject.toml` REMAINS AN ANSWER**, and that is the one outcome
that is NOT a failure: a repo with no `pyproject.toml` has no explicit Ruff
`select`, so there is no backstop to be absent from and no gaps to report. The
pin-walker ruling — `is_file` is an answer — applies unchanged.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeVar

# Carried rather than inherited from an importer: a bare `from returns...`
# import resolves only if some module up the chain happens to have inserted
# `_vendor/` already, which is a property of the caller. That state is what
# broke the fleet's release fan-out for seven hours on 2026-07-30.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware.

__all__: list[str] = ["RuffProbeUnavailable", "find_ruff_backstop_gaps"]

_Captured = TypeVar("_Captured")

_RUFF_BLE001_SETTING = "blind-except (BLE001)"
_RUFF_EXCLUDED_REASON = "inspected file is excluded from Ruff; BLE001 backstop is absent"
_RUFF_NO_BLE_REASON = "Ruff lint select does not enable BLE/BLE001 for inspected file"


@dataclass(frozen=True, kw_only=True)
class RuffProbeUnavailable:
    """The BLE001 backstop could not be PROBED, and WHICH read failed.

    ⛔ "COULD NOT PROBE" IS NOT "NO GAPS", and keeping them apart is the whole
    point: the old shape reported the second when it meant the first, so a
    repo whose Ruff was broken read as a repo whose Ruff was fine.

    `reason` is the discriminator a caller branches on; `detail` is the
    operator-facing evidence. The four want different responses — an unreadable
    `pyproject.toml` is a broken checkout, an absent `ruff` is a broken
    environment, and a failing invocation is a broken Ruff configuration.
    """

    reason: Literal[
        "pyproject-not-read",
        "ruff-not-run",
        "ruff-show-files-failed",
        "ruff-show-settings-failed",
    ]
    detail: str


def _captured(*, result: IOResult[_Captured, RuffProbeUnavailable]) -> list[_Captured]:
    """The success value as a 0-or-1 list — the shape-agnostic unwrap.

    `.map` runs ONLY on the success track, so an empty list IS the failure
    track and no `unsafe_perform_io` escape is needed to read the value. Every
    call site here sits directly under its own failure-track return, so the
    list is non-empty exactly because the failure was already returned.
    ⛔ `value_or` is the trap this avoids: on an `IOResult` it yields an
    `IO[...]` that compares unequal to every payload. `.bind` is absent for a
    different reason — it types as partially-unknown under this repo's pyright
    settings, which is why no module in this package calls it.
    """
    out: list[_Captured] = []
    _ = result.map(out.append)
    return out


def _unavailable(
    *,
    reason: Literal[
        "pyproject-not-read",
        "ruff-not-run",
        "ruff-show-files-failed",
        "ruff-show-settings-failed",
    ],
    detail: str,
) -> IOFailure[RuffProbeUnavailable]:
    """One construction site for the failure track, so every arm carries both fields."""
    return IOFailure(RuffProbeUnavailable(reason=reason, detail=detail))


def _run_ruff(
    *, repo_root: Path, args: list[str]
) -> IOResult[subprocess.CompletedProcess[str], RuffProbeUnavailable]:
    """Invoke `ruff` once, carrying a `ruff` that never RAN apart from one that failed.

    The catch is NARROW and ENUMERATED (`OSError`), which is the sanctioned
    hand-rolled seam lift: `ruff` absent from PATH, a `ruff` that cannot be
    exec'd, a fork failure. A bug raised in here still propagates.
    """
    try:
        return IOSuccess(
            subprocess.run(
                ["ruff", *args],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
        )
    except OSError as not_run:
        return _unavailable(reason="ruff-not-run", detail=str(not_run))


def _explicit_ruff_lint_select_configured(
    *, repo_root: Path
) -> IOResult[bool, RuffProbeUnavailable]:
    """Whether the repo configures an explicit Ruff `select`, or WHY that is unknown.

    An ABSENT `pyproject.toml` is an ANSWER (`False` — no explicit select), not
    a failure. An UNREADABLE one is a failure: `is_file()` then `read_text()`
    fused those two and left the read uncaught behind it.
    """
    pyproject = repo_root / "pyproject.toml"
    try:
        text = pyproject.read_text(encoding="utf-8")
    except FileNotFoundError:
        # An absent pyproject is an ANSWER: no explicit select, so no backstop
        # to be absent from. Bound rather than inlined so the `IOSuccess(...)`
        # argument is a NAME — a bare literal reads to ruff (FBT003) as a
        # boolean flag argument, which this is not.
        no_explicit_select = False
        return IOSuccess(no_explicit_select)
    except OSError as unreadable:
        return _unavailable(reason="pyproject-not-read", detail=str(unreadable))
    configured = "[tool.ruff.lint]" in text and "select" in text
    return IOSuccess(configured)


def _ruff_show_files(
    *, repo_root: Path, scan_roots: tuple[Path, ...]
) -> IOResult[frozenset[Path], RuffProbeUnavailable]:
    """The files Ruff will lint, or WHY the enumeration did not happen.

    ⛔ THE `returncode` IS READ NOW AND WAS NOT BEFORE. A failed enumeration
    yields empty stdout, and an empty answer here makes EVERY inspected file
    look excluded from Ruff — a gap manufactured for every file in the repo,
    blamed on exclusion rules, from a Ruff that never produced a listing.
    """
    probed = _run_ruff(
        repo_root=repo_root,
        args=["check", "--show-files", "--force-exclude", *(str(path) for path in scan_roots)],
    )
    if isinstance(probed, IOFailure):
        return probed
    result = _captured(result=probed)[0]
    if result.returncode != 0:
        return _unavailable(
            reason="ruff-show-files-failed",
            detail=f"exit {result.returncode}: {result.stderr.strip()}",
        )
    resolved_root = repo_root.resolve()
    return IOSuccess(
        frozenset(
            Path(line).resolve().relative_to(resolved_root) for line in result.stdout.splitlines()
        )
    )


def _ruff_enables_ble001(
    *, repo_root: Path, rel_path: Path
) -> IOResult[bool, RuffProbeUnavailable]:
    """Whether BLE001 is enabled for `rel_path`, or WHY that is unknown.

    ⛔ A NON-ZERO EXIT IS NO LONGER FUSED WITH "BLE001 IS OFF". The old
    `result.returncode == 0 and <setting> in result.stdout` reported a broken
    invocation to the operator as a verdict about their `select` list.
    """
    probed = _run_ruff(repo_root=repo_root, args=["check", "--show-settings", str(rel_path)])
    if isinstance(probed, IOFailure):
        return probed
    result = _captured(result=probed)[0]
    if result.returncode != 0:
        return _unavailable(
            reason="ruff-show-settings-failed",
            detail=f"{rel_path}: exit {result.returncode}: {result.stderr.strip()}",
        )
    return IOSuccess(_RUFF_BLE001_SETTING in result.stdout)


def find_ruff_backstop_gaps(
    *, repo_root: Path, scan_roots: tuple[Path, ...], inspected_files: tuple[Path, ...]
) -> IOResult[list[tuple[Path, str]], RuffProbeUnavailable]:
    """Inspected files Ruff will not lint with BLE001 enabled, or WHY that is unknown.

    `scan_roots` is what Ruff is asked to enumerate. It used to be the caller's
    declared `source_trees`; with a git-derived universe the caller passes the
    repo root, so the enumeration covers the same files the universe does.

    ⛔ AN EMPTY LIST NOW MEANS "PROBED, AND THERE ARE NO GAPS" — nothing else.
    It used to also mean "the `pyproject.toml` could not be read", which is the
    vacuous pass `livespec-dev-tooling-8o8e.5` filed.
    """
    configured = _explicit_ruff_lint_select_configured(repo_root=repo_root)
    if isinstance(configured, IOFailure):
        return configured
    if not _captured(result=configured)[0]:
        return IOSuccess([])
    listed = _ruff_show_files(repo_root=repo_root, scan_roots=scan_roots)
    if isinstance(listed, IOFailure):
        return listed
    ruff_files = _captured(result=listed)[0]
    gaps: list[tuple[Path, str]] = []
    for rel_path in inspected_files:
        if rel_path not in ruff_files:
            gaps.append((rel_path, _RUFF_EXCLUDED_REASON))
            continue
        enabled = _ruff_enables_ble001(repo_root=repo_root, rel_path=rel_path)
        if isinstance(enabled, IOFailure):
            return enabled
        if not _captured(result=enabled)[0]:
            gaps.append((rel_path, _RUFF_NO_BLE_REASON))
    return IOSuccess(gaps)

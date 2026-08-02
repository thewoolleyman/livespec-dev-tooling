"""LOCAL-vantage beads-runtime detect-and-guide rows for the fleet contract.

The beads ledger backend has host-level and checkout-level prerequisites that
`just bootstrap` (and the local first-touch reconcile it delegates to)
deliberately does NOT provision — the `bd` query binary, a reachable Dolt
`sql-server`, the injected tenant secret, and the committed `.beads/` pointer
files (per `livespec/AGENTS.md` §"Beads runtime prerequisites"). These rows make
the verb DETECT-AND-GUIDE them: each PROBES one prerequisite and, when unmet,
emits a WARNING-severity finding carrying a copy-pasteable guided TODO — surfaced
to the operator, never machine-faked, and (because the verb's reconcile loop
treats a `warning` finding as guidance, not an unresolved row) never failing the
verb. The human resolves the seam out of band.

Every row is GATED on a `.beads/` directory: a repo that is not beads-backed
SKIPs each beads-runtime row rather than emitting a false finding (the same
applicability gate `reconcile_beads_dir_perms` uses).

Secrets are PROBE-ONLY: presence is checked with `test -n` through the command
seam, so the value is NEVER read into a variable, echoed, or logged. Every probe
routes through the `LocalContext` command seam or a filesystem read on the
checkout, so the rows stay hermetically testable with a canned-response runner.
"""

from __future__ import annotations

import sys
from pathlib import Path

# `returns` is VENDORED, not installed, so a bare import resolves only if some
# EARLIER import in the same process already put `_vendor/` on `sys.path`.
# Relying on that ordering is what broke the fleet's release fan-out for seven
# hours (`vzwa`'s `89296e0`), and `test_vendor_update` enforces this preamble on
# every `returns`-importing module for exactly that reason.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.fleet._context import (  # noqa: E402
    RowFinding,
    RowOutcome,
    RowPass,
    RowSkip,
    row_excluded,
)
from livespec_dev_tooling.fleet._invocation_failure import (  # noqa: E402
    InvocationNotPerformed,
)
from livespec_dev_tooling.fleet._local_context import (  # noqa: E402
    LocalContext,
    command_answer,
)

__all__: list[str] = [
    "DOLT_SERVER_HOST",
    "DOLT_SERVER_PORT",
    "reconcile_beads_bd_binary",
    "reconcile_beads_config_committed",
    "reconcile_beads_dolt_server",
    "reconcile_beads_metadata_present",
    "reconcile_beads_tenant_secret",
]


# The fleet tenants force TCP (the dolt unix socket is unreachable by sandboxed
# callers), so `.beads/config.yaml` carries these host/port keys and no socket key.
DOLT_SERVER_HOST = "127.0.0.1"
DOLT_SERVER_PORT = 3307

_PREREQ_DOC = 'AGENTS.md §"Beads runtime prerequisites"'
_EXCLUDED_NO_BEADS = "no .beads tenant directory (not a beads-backed repo)"


def _unprobed(*, failure: InvocationNotPerformed) -> RowFinding:
    """The finding for a prerequisite whose PROBE never ran.

    Distinct from every unmet-prerequisite finding below, and deliberately
    so: those carry a guided TODO telling the operator how to satisfy the
    prerequisite, which is wrong advice when nothing was measured. The
    prerequisite may well be satisfied — the probe simply never asked.
    Kept at `warning` severity like its siblings, because an unrunnable
    probe is the same out-of-band human seam, not an unmet obligation.
    """
    return RowFinding(
        severity="warning",
        message=(
            f"beads prerequisite left UNPROBED (nothing was measured, so the "
            f"prerequisite is neither met nor unmet): {failure.reason}"
        ),
    )


def _beads_gate(*, ctx: LocalContext) -> RowOutcome | None:
    """The outcome that ENDS a beads row, or None when the row should proceed.

    ⛔ EVERY BEADS ROW CALLS THIS FIRST, WHICH IS WHY IT IS THE SHARED CAUSE.
    It used to be `(ctx.checkout / ".beads").is_dir()`, a primitive that RAISES:
    `pathlib` ignores only `(ENOENT, ENOTDIR, EBADF, ELOOP)`, so `EACCES`
    propagated out of whichever row asked and aborted the whole local reconcile.
    Fixing only the row whose own primitive appeared in an offender list would
    have moved the count and left the crash live in all five.

    THREE OUTCOMES, and the middle one is the point: the directory is there
    (proceed), it is genuinely absent (INAPPLICABLE — an excluded pass), or it
    could not be evaluated (`RowSkip`, whose ratified meaning is exactly
    "can't-read is not absent"). The old probe fused the last two.
    """
    applicable = ctx.dir_present(path=ctx.checkout / ".beads")
    if isinstance(applicable, IOFailure):
        not_read = unsafe_perform_io(applicable.failure())
        return RowSkip(reason=f".beads applicability not evaluable ({not_read.kind})")
    if not unsafe_perform_io(applicable.unwrap()):
        return row_excluded(reason=_EXCLUDED_NO_BEADS)
    return None


def reconcile_beads_bd_binary(*, ctx: LocalContext) -> RowOutcome:
    """Probe the explicit bd override, or fall back to executable `bd` on PATH."""
    gate = _beads_gate(ctx=ctx)
    if gate is not None:
        return gate
    probe = command_answer(
        outcome=ctx.exec(
            args=[
                "bash",
                "-c",
                'if test -n "${LIVESPEC_BD_PATH:-}"; then '
                'test -x "$LIVESPEC_BD_PATH"; '
                'else bd_path="$(command -v bd 2>/dev/null)" && '
                'test -n "$bd_path" && test -x "$bd_path"; fi',
            ]
        )
    )
    if isinstance(probe, InvocationNotPerformed):
        return _unprobed(failure=probe)
    if probe.returncode == 0:
        return RowPass(note="bd binary present and executable via LIVESPEC_BD_PATH or PATH")
    return RowFinding(
        severity="warning",
        message=(
            "beads `bd` binary unavailable: set LIVESPEC_BD_PATH to the guarded pinned bd "
            "(v1.0.5, e.g. /usr/local/bin/bd), or install the guarded `bd` on PATH "
            f"— see {_PREREQ_DOC}"
        ),
    )


def reconcile_beads_dolt_server(*, ctx: LocalContext) -> RowOutcome:
    """Probe that the Dolt sql-server is reachable over TCP `127.0.0.1:3307`."""
    gate = _beads_gate(ctx=ctx)
    if gate is not None:
        return gate
    probe = command_answer(
        outcome=ctx.exec(
            args=[
                "timeout",
                "2",
                "bash",
                "-c",
                f"exec 3<>/dev/tcp/{DOLT_SERVER_HOST}/{DOLT_SERVER_PORT}",
            ]
        )
    )
    if isinstance(probe, InvocationNotPerformed):
        return _unprobed(failure=probe)
    if probe.returncode == 0:
        return RowPass(note=f"Dolt sql-server reachable at {DOLT_SERVER_HOST}:{DOLT_SERVER_PORT}")
    return RowFinding(
        severity="warning",
        message=(
            f"Dolt sql-server unreachable at {DOLT_SERVER_HOST}:{DOLT_SERVER_PORT}: start the "
            f"running Dolt sql-server (TCP-only; .beads/config.yaml carries dolt.* host/port "
            f"keys with no socket key) — see {_PREREQ_DOC}"
        ),
    )


def reconcile_beads_tenant_secret(*, ctx: LocalContext) -> RowOutcome:
    """Probe-ONLY that `BEADS_DOLT_PASSWORD` is present (value never read or echoed)."""
    gate = _beads_gate(ctx=ctx)
    if gate is not None:
        return gate
    probe = command_answer(
        outcome=ctx.exec(args=["bash", "-c", 'test -n "${BEADS_DOLT_PASSWORD:-}"'])
    )
    if isinstance(probe, InvocationNotPerformed):
        return _unprobed(failure=probe)
    if probe.returncode == 0:
        return RowPass(note="BEADS_DOLT_PASSWORD present (probe-only; value never read)")
    return RowFinding(
        severity="warning",
        message=(
            "tenant secret BEADS_DOLT_PASSWORD absent: run under the configured 1Password env "
            "wrapper (e.g. with-livespec-env.sh) so the bare tenant password is injected at "
            f"bd-call time — never commit it — see {_PREREQ_DOC}"
        ),
    )


def reconcile_beads_config_committed(*, ctx: LocalContext) -> RowOutcome:
    """Probe that `.beads/config.yaml` (the committed tenant pointer) is tracked."""
    gate = _beads_gate(ctx=ctx)
    if gate is not None:
        return gate
    probe = command_answer(
        outcome=ctx.exec(args=["git", "ls-files", "--error-unmatch", ".beads/config.yaml"])
    )
    if isinstance(probe, InvocationNotPerformed):
        return _unprobed(failure=probe)
    if probe.returncode == 0:
        return RowPass(note=".beads/config.yaml is committed")
    return RowFinding(
        severity="warning",
        message=(
            "committed pointer .beads/config.yaml is not tracked: commit the tenant config.yaml "
            f"(the dolt.* server host/port keys, no socket key) — see {_PREREQ_DOC}"
        ),
    )


def reconcile_beads_metadata_present(*, ctx: LocalContext) -> RowOutcome:
    """Probe that `.beads/metadata.json` (regenerable, gitignored) is present."""
    gate = _beads_gate(ctx=ctx)
    if gate is not None:
        return gate
    present = ctx.file_present(path=ctx.checkout / ".beads" / "metadata.json")
    if isinstance(present, IOFailure):
        not_read = unsafe_perform_io(present.failure())
        return RowSkip(reason=f".beads/metadata.json not evaluable ({not_read.kind})")
    if unsafe_perform_io(present.unwrap()):
        return RowPass(note=".beads/metadata.json present")
    return RowFinding(
        severity="warning",
        message=(
            "regenerable pointer .beads/metadata.json absent: regenerate it by running "
            "`bd init --server` in a /tmp scratch dir with this repo's .beads/config.yaml "
            f"(project_id is server-stable) and copying its metadata.json in — see {_PREREQ_DOC}"
        ),
    )

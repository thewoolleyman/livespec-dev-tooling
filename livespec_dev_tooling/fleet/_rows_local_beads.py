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

from livespec_dev_tooling.fleet._context import RowFinding, RowOutcome, RowPass, RowSkip
from livespec_dev_tooling.fleet._invocation_failure import InvocationNotPerformed
from livespec_dev_tooling.fleet._local_context import LocalContext, command_answer

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
_SKIP_NO_BEADS = "no .beads tenant directory (not a beads-backed repo)"


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


def _beads_applicable(*, ctx: LocalContext) -> bool:
    """True when the checkout carries a `.beads/` tenant directory."""
    return (ctx.checkout / ".beads").is_dir()


def reconcile_beads_bd_binary(*, ctx: LocalContext) -> RowOutcome:
    """Probe the explicit bd override, or fall back to executable `bd` on PATH."""
    if not _beads_applicable(ctx=ctx):
        return RowSkip(reason=_SKIP_NO_BEADS)
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
    if not _beads_applicable(ctx=ctx):
        return RowSkip(reason=_SKIP_NO_BEADS)
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
    if not _beads_applicable(ctx=ctx):
        return RowSkip(reason=_SKIP_NO_BEADS)
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
    if not _beads_applicable(ctx=ctx):
        return RowSkip(reason=_SKIP_NO_BEADS)
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
    if not _beads_applicable(ctx=ctx):
        return RowSkip(reason=_SKIP_NO_BEADS)
    if (ctx.checkout / ".beads" / "metadata.json").is_file():
        return RowPass(note=".beads/metadata.json present")
    return RowFinding(
        severity="warning",
        message=(
            "regenerable pointer .beads/metadata.json absent: regenerate it by running "
            "`bd init --server` in a /tmp scratch dir with this repo's .beads/config.yaml "
            f"(project_id is server-stable) and copying its metadata.json in — see {_PREREQ_DOC}"
        ),
    )

"""The gates credential's HOST-SIDE facts — which file, readable by whom, which wrapper.

The delegated gate has two halves that must agree about one file and could not
see each other: the SWITCH side (`gate_remote_delegate`), which decides whether
a push may delegate at all, and the CLUSTER side (`gate_remote_client`), which
issues the commands that authenticate. This module is the one place that names
the file, so the two halves cannot drift apart.

WHY THE SWITCH ALONE WAS NOT ENOUGH, measured 2026-10-11. `delegated_gate` lives
in the consuming repository's `pyproject.toml`, which travels with the CODE and
says nothing about the HOST. A repository that opted in therefore delegated from
every host that cloned it — a Fabro sandbox included — and a host with no gates
credential fails closed, which is correct for a gate and fatal for a factory:
the push is refused and nothing says why. Eligibility is a property of the host,
so it is read FROM the host, here.

EVERY CLUSTER COMMAND GOES THROUGH THE WRAPPER, and the wrapper is not an
implementation detail of this module's own choosing: it is the component that
refreshes the credential when the API server rejects it (the gates
ServiceAccount's token is recreated at every control-plane boot, so the first
call after one is EXPECTED to be a 401). A client that ran `kubectl` directly
would authenticate with whatever `KUBECONFIG` the pushing user's shell happened
to carry — on the VPS login user, none at all — and would never reach the
refresh. So the prefix is applied here and the client cannot opt out of it.

ONE ENV VAR, HONOURED BY BOTH SIDES. `GATES_KUBECONFIG` is what the shipped
`with-gates-kubeconfig` resolves `KUBECONFIG` from, so this module reads the
SAME variable with the SAME default: the file the eligibility probe tested is
then necessarily the file the wrapper authenticates with, rather than two
answers that happen to coincide on a converged host and diverge on any other.
`tests/livespec_dev_tooling/test_gate_credential.py` holds the three constants
against the wrapper's own bytes and the role's own destination.

AND THIS MODULE IS ALSO WHERE THE WRAPPER'S ANSWER IS READ, not only where its
command is built, because a refresh that WORKED used to leave no trace. Every
cluster command a delegated push issues runs CAPTURED rather than streamed, and
a captured stderr is read only when the step failed: `require_success` carries
it as the failing step's `detail`, and a step that succeeded produces none. So
the wrapper's refresh line reached the operator exactly when the push was ALSO
refused. Measured 2026-10-21 on master v1.120.0 (6728f5ad) — a credential that
goes stale at every control-plane boot and silently heals itself on the retry
was indistinguishable from one that never went stale, and nothing told anyone
there was a thing to fix. `with_wrapper_notices` closes that, at the same seam
and for the same reason the prefix is applied here: the wrapper is this module's
subject, in both directions.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from livespec_dev_tooling.gate_remote_invocation import GateCommandOutcome, GateCommandRunner

# `structlog` is VENDORED, not installed; a bare import here would resolve only
# when some earlier import in the process happened to run first.
_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import.

__all__: list[str] = [
    "GATES_KUBECONFIG_DEFAULT",
    "GATES_KUBECONFIG_ENV",
    "GATES_WRAPPER",
    "WRAPPER_NOTICE_PREFIX",
    "gates_kubeconfig_path",
    "gates_kubeconfig_readable",
    "with_gates_kubeconfig",
    "with_wrapper_notices",
    "wrapper_notices",
]

# Where the `gates_kubeconfig` role installs the credential, and the default the
# shipped wrapper falls back to. LOCKSTEP WITH BOTH — neither file can see this
# one, and a drift is an eligibility probe reading one file while the wrapper
# authenticates with another.
GATES_KUBECONFIG_DEFAULT = Path("/etc/ci-runner/gates.kubeconfig")

# The override both sides honour. Named rather than inlined because the tests
# that keep this module and the wrapper in step read it from here.
GATES_KUBECONFIG_ENV = "GATES_KUBECONFIG"

# The credential wrapper the role installs beside the credential: it exports
# `KUBECONFIG`, recognises the API server's rejection, refreshes the credential
# once, and retries. Invoked by NAME, resolved from `PATH`, so a host that has
# not been converged fails at the seam as a command that did not run — which the
# client reports as a gate that reached no verdict, never as a pass.
GATES_WRAPPER = "with-gates-kubeconfig"

# What every line the wrapper writes ABOUT ITSELF starts with, and the only thing
# that tells those lines apart from the output of the command it carried. The
# wrapper writes `with-gates-kubeconfig: credential rejected — refreshing once
# and retrying` to stderr before it refreshes, and a refusal to refresh under its
# own name too. LOCKSTEP WITH THE SHIPPED SCRIPT like the constants above:
# `tests/livespec_dev_tooling/test_gate_remote_delegate.py` drives the wrapper's
# OWN refresh line, read out of that file, rather than a restatement of it.
WRAPPER_NOTICE_PREFIX = f"{GATES_WRAPPER}:"


def gates_kubeconfig_path() -> Path:
    """Name the gates kubeconfig this host would authenticate with.

    An EMPTY override is treated as absent rather than as the path `""`: an
    exported-but-empty variable is how a shell says "unset" in practice, and the
    wrapper's own `${GATES_KUBECONFIG:-<default>}` expansion falls back on it
    too, so reading it as a real path would make the two halves disagree.
    """
    declared = os.environ.get(GATES_KUBECONFIG_ENV)
    if declared:
        return Path(declared)
    return GATES_KUBECONFIG_DEFAULT


def gates_kubeconfig_readable() -> bool:
    """Answer whether THIS user, on THIS host, can read the gates credential.

    `is_file` AND `os.access`, because either alone answers a different
    question. A readable directory at the credential's path is not a credential,
    and a file this user cannot open is not one either — the VPS case the whole
    change exists for, where the credential was `root:root 0600` while pushes
    run as the login user.

    Deliberately NOT a probe of the cluster: whether the credential still
    AUTHENTICATES is the wrapper's business (it refreshes a rejected one), and a
    reachability test here would make a momentary network fault look like an
    ineligible host and silently gate locally instead of refusing.
    """
    credential = gates_kubeconfig_path()
    return credential.is_file() and os.access(credential, os.R_OK)


def with_gates_kubeconfig(*, argv: list[str]) -> list[str]:
    """Prefix one cluster command with the credential wrapper.

    A PREFIX, not a rewrite: the command reaches the wrapper verbatim, so what
    the client asked the cluster is exactly what runs and a reader of the failed
    step's `argv` sees both the wrapper and the command it carried.
    """
    return [GATES_WRAPPER, *argv]


def wrapper_notices(*, stderr: str) -> tuple[str, ...]:
    """The wrapper's OWN lines out of one captured stderr, and nothing else.

    NARROW ON PURPOSE. A cluster command's stderr carries whatever `kubectl` had
    to say as well, and keeping that noise OFF the operator's terminal is exactly
    why the client captures these streams rather than streaming them. Handing the
    whole stream over on success would put every deprecation warning and retry
    hint in front of a push and bury the one line that means something. The
    prefix is what separates the wrapper's account of itself from the output of
    the command it carried.
    """
    return tuple(line for line in stderr.splitlines() if line.startswith(WRAPPER_NOTICE_PREFIX))


def _notices_to_narrate(*, outcome: GateCommandOutcome) -> tuple[str, ...]:
    """The wrapper notices of an invocation that RAN AND SUCCEEDED, or none.

    SUCCESS ONLY, and the asymmetry is the whole point. A step that FAILED
    already reports its entire captured stderr as the failing step's `detail`,
    which the push's refusal prints, so narrating here as well would say the
    same thing twice. The gap this closes is the opposite one: a rejection the
    wrapper's retry REPAIRED leaves a step that succeeded, whose stderr nothing
    anywhere goes on to read.

    A command that never RAN carries no streams at all, so it answers none —
    `value_or` rather than a branch, because "did not happen" and "ran and said
    nothing" want the identical, empty answer here.
    """
    return outcome.map(
        lambda ran: wrapper_notices(stderr=ran.stderr) if ran.returncode == 0 else ()
    ).value_or(())


def with_wrapper_notices(*, runner: GateCommandRunner) -> GateCommandRunner:
    """Wrap `runner` so the wrapper's own notices reach the operator's terminal.

    A DECORATOR AT THE SEAM, which is what makes it unskippable: the same
    argument `with_gates_kubeconfig` makes for the command, applied to the
    ANSWER. Every command one delegated push issues goes through a single runner,
    so wrapping that runner once covers the submit, every poll, the pod read and
    the assembly reaches too, and no step can be spelled in a way that drops the
    narration.

    The notice is re-emitted as the log EVENT, verbatim, rather than summarised:
    an operator reading a push's output is looking for the wording the wrapper
    writes on a host, and a paraphrase would not be it.
    """
    log = structlog.get_logger("gate_credential")

    def narrated(
        *,
        argv: list[str],
        cwd: Path,
        stdin: str | None = None,
        stream: bool = False,
    ) -> GateCommandOutcome:
        outcome = runner(argv=argv, cwd=cwd, stdin=stdin, stream=stream)
        for notice in _notices_to_narrate(outcome=outcome):
            log.warning(notice)
        return outcome

    return narrated

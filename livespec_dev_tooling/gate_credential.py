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
"""

from __future__ import annotations

import os
from pathlib import Path

__all__: list[str] = [
    "GATES_KUBECONFIG_DEFAULT",
    "GATES_KUBECONFIG_ENV",
    "GATES_WRAPPER",
    "gates_kubeconfig_path",
    "gates_kubeconfig_readable",
    "with_gates_kubeconfig",
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

"""The gates credential's host-side facts — which file, readable by whom, which wrapper.

Nothing here touches `/etc/ci-runner`, a cluster, or a credential. The two
questions this module answers are answered against `tmp_path` and the
environment variable the shipped wrapper itself reads, so the suite runs
identically on a host that holds the credential and on one that never will.

THE LOCKSTEP TEST IS THE LOAD-BEARING ONE. Three separately-authored files have
to name the SAME file for a delegated gate to work at all: this module (which
decides whether a push may delegate), the shipped `with-gates-kubeconfig`
wrapper (which exports it as `KUBECONFIG`), and the `gates_kubeconfig` role
(which installs it). None of the three can see the other two, and a drift
between them is a syntax error in none: it is an eligibility probe that reads
one file while the wrapper authenticates with another, which presents as a push
that delegates and then fails 401 on the VPS — a long way from the edit that
caused it. So the constants are held against the shipped bytes rather than
restated.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_dev_tooling.gate_credential import (
    GATES_KUBECONFIG_DEFAULT,
    GATES_KUBECONFIG_ENV,
    GATES_WRAPPER,
    gates_kubeconfig_path,
    gates_kubeconfig_readable,
    with_gates_kubeconfig,
)

if TYPE_CHECKING:
    import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROLE = _REPO_ROOT / "ansible" / "roles" / "gates_kubeconfig"
_WRAPPER_SCRIPT = _ROLE / "files" / "with-gates-kubeconfig"
_ROLE_DEFAULTS = _ROLE / "defaults" / "main.yml"

# The wrapper's own `export KUBECONFIG="${GATES_KUBECONFIG:-<default>}"`, read for
# BOTH halves at once: the variable name it honours and the path it falls back to.
_WRAPPER_KUBECONFIG = re.compile(r'export KUBECONFIG="\$\{(?P<env>[A-Z_]+):-(?P<default>[^"}]+)\}"')
# The role's destination for the credential it installs.
_ROLE_DEST = re.compile(r"^gates_kubeconfig_dest: (?P<path>\S+)$", re.MULTILINE)


def _wrapper_credential() -> tuple[str, str]:
    """The env var and default path the shipped wrapper resolves `KUBECONFIG` from."""
    found = _WRAPPER_KUBECONFIG.search(_WRAPPER_SCRIPT.read_text(encoding="utf-8"))
    assert found is not None, (
        f"{_WRAPPER_SCRIPT.name} must export KUBECONFIG from a "
        f"`${{<VAR>:-<default>}}` expansion; this test reads the credential it "
        f"authenticates with out of that line rather than restating it, so a "
        f"wrapper that resolves its kubeconfig some other way is a test that has "
        f"stopped checking anything"
    )
    return found["env"], found["default"]


def test_the_client_and_the_wrapper_and_the_role_name_one_credential() -> None:
    """The eligibility probe, the wrapper and the installer agree, by measurement."""
    env, default = _wrapper_credential()
    installed = _ROLE_DEST.search(_ROLE_DEFAULTS.read_text(encoding="utf-8"))

    assert env == GATES_KUBECONFIG_ENV
    assert default == str(GATES_KUBECONFIG_DEFAULT)
    assert installed is not None
    assert installed["path"] == str(GATES_KUBECONFIG_DEFAULT)


def test_the_wrapper_named_here_is_the_script_the_role_ships() -> None:
    """A prefix naming a program the role does not install is a gate that cannot run."""
    assert _WRAPPER_SCRIPT.name == GATES_WRAPPER
    assert _WRAPPER_SCRIPT.is_file()


def test_the_credential_defaults_to_the_installed_path(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """With nothing declared, the path is the one the role converges."""
    monkeypatch.delenv(GATES_KUBECONFIG_ENV, raising=False)

    assert gates_kubeconfig_path() == GATES_KUBECONFIG_DEFAULT


def test_the_environment_can_name_another_credential(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same override the wrapper honours, so both halves move together."""
    elsewhere = tmp_path / "gates.kubeconfig"
    monkeypatch.setenv(GATES_KUBECONFIG_ENV, str(elsewhere))

    assert gates_kubeconfig_path() == elsewhere


def test_a_host_holding_the_credential_is_eligible(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A readable credential file is what makes a push able to delegate."""
    credential = tmp_path / "gates.kubeconfig"
    _ = credential.write_text("kind: Config\n", encoding="utf-8")
    monkeypatch.setenv(GATES_KUBECONFIG_ENV, str(credential))

    assert gates_kubeconfig_readable() is True


def test_a_host_holding_no_credential_is_not_eligible(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The factory-sandbox case, and the one this very suite runs in.

    Asserted on ABSENCE rather than on a mode-0000 file on purpose: a suite run
    as root reads a 0000 file perfectly well, so a permission-bit fixture would
    answer "eligible" under root and "ineligible" under a login user — the one
    shape a test must never have.
    """
    monkeypatch.setenv(GATES_KUBECONFIG_ENV, str(tmp_path / "absent.kubeconfig"))

    assert gates_kubeconfig_readable() is False


def test_a_credential_path_that_is_not_a_file_is_not_eligible(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A directory at the credential's path is readable and is not a credential."""
    monkeypatch.setenv(GATES_KUBECONFIG_ENV, str(tmp_path))

    assert gates_kubeconfig_readable() is False


def test_a_cluster_command_is_handed_to_the_wrapper_unchanged() -> None:
    """The wrapper PREFIXES; it never re-shapes the command it carries."""
    wrapped = with_gates_kubeconfig(argv=["kubectl", "--namespace", "gates", "get", "jobs"])

    assert wrapped == [GATES_WRAPPER, "kubectl", "--namespace", "gates", "get", "jobs"]

"""`fabro-server-verify-web` takes its canonical host from the instance, never from a default.

A machine is bound ONLY through the inventory's host groups and host variables
(livespec-dev-tooling-prdxxe). The readiness gate the `fabro_server` role installs
carried `vps.perch-rudd.ts.net:32276` as the default for `FABRO_CANONICAL_HOST`,
which is a second, silent place that binding lived — and the WRONG one on every
instance except the one it was measured on. A default like that cannot fail
loudly: the script sends a `Host:` header for somebody else's server, the reverse
proxy answers 404, and the unit reports the console unverified rather than
reporting that nobody told it which host it serves.

So the script REFUSES when the variable is unset, naming it, and the role renders
it from the instance's own `canonical_host`.

WHY THE SCRIPT IS RUN RATHER THAN READ. The claim is about CONTROL FLOW — refuse
BEFORE any request is attempted — and reading a shell script cannot establish
that. It runs with `curl` faked on a scratch PATH, so no host is contacted and the
absence of a request is itself an assertion.

Work-item: livespec-dev-tooling-mavj5i. Plan: livespec-orchestrator-beads-fabro
`petri-factory-on-gmktec`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROLE = _REPO_ROOT / "ansible" / "roles" / "fabro_server"
_VERIFY_WEB = _ROLE / "files" / "fabro-server-verify-web"
_UNIT_TEMPLATE = _ROLE / "templates" / "fabro-server.service.j2"

# The variable the unit carries and the script must be told. Spelled once, and
# asserted on both halves, because a disagreement between them is a readiness
# gate that refuses on a converged host.
_CANONICAL_HOST_VAR = "FABRO_CANONICAL_HOST"

# `curl`: log the argv and answer nothing. A run that reaches it has already
# failed this suite's question, so it never needs to succeed.
_CURL_SHIM = 'printf \'curl %s\\n\' "$*" >> "$ARGV_LOG"\nexit 1\n'


def _shim(*, bin_dir: Path, name: str, body: str) -> None:
    """One executable on the scratch PATH, standing in for a host tool."""
    path = bin_dir / name
    _ = path.write_text(f"#!/usr/bin/env bash\n{body}", encoding="utf-8")
    path.chmod(0o755)


def _run_verify(*, tmp_path: Path, canonical_host: str | None) -> tuple[int, str, list[str]]:
    """Run the shipped readiness gate with `FABRO_CANONICAL_HOST` set or absent."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "argv.log"
    _shim(bin_dir=bin_dir, name="curl", body=_CURL_SHIM)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("COVERAGE_", "COV_CORE_"))}
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["ARGV_LOG"] = str(log)
    # One attempt: the retry loop's DURATION is not what is under test, and a
    # refusal must happen before the first attempt anyway.
    env["FABRO_WEB_VERIFY_ATTEMPTS"] = "1"
    env.pop(_CANONICAL_HOST_VAR, None)
    if canonical_host is not None:
        env[_CANONICAL_HOST_VAR] = canonical_host
    completed = subprocess.run(
        ["bash", str(_VERIFY_WEB)],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    invoked = log.read_text(encoding="utf-8").splitlines() if log.is_file() else []
    return completed.returncode, completed.stdout + completed.stderr, invoked


def test_bash_is_available_to_run_the_shipped_readiness_gate() -> None:
    """The lens this suite reads the script through, named rather than assumed."""
    assert shutil.which("bash") is not None


def test_the_readiness_gate_refuses_before_it_contacts_anything(*, tmp_path: Path) -> None:
    """The refusal comes FIRST, names the variable, and no request is attempted.

    `curl` is faked and its argv logged, so an empty log is the assertion: a gate
    that sent even one request with the wrong `Host:` header would be asking a
    reverse proxy about somebody else's server.

    Asserted as a REFUSAL rather than as the absence of a default, because the
    absence of a default under `set -u` would also be satisfied by an unbound
    variable expanding to nothing — which is a `Host:` header of the empty string
    and a gate that fails for a reason it never states.
    """
    code, output, invoked = _run_verify(tmp_path=tmp_path, canonical_host=None)

    assert code != 0
    assert _CANONICAL_HOST_VAR in output
    assert invoked == []


def test_the_readiness_gate_runs_when_the_instance_supplies_its_canonical_host(
    *, tmp_path: Path
) -> None:
    """The control arm: told which host it serves, the gate proceeds to its probes.

    The faked `curl` fails, so the run still exits non-zero — what this asserts is
    that the gate GOT THERE, carrying the supplied host into the `Host:` header.
    """
    supplied = "an-instance.example.ts.net:32276"

    code, _output, invoked = _run_verify(tmp_path=tmp_path, canonical_host=supplied)

    assert code != 0
    assert invoked != []
    assert any(f"Host: {supplied}" in line for line in invoked)


def test_the_role_renders_the_canonical_host_from_the_instance() -> None:
    """The other half of the pair: the unit carries the per-instance fact.

    The role acts on ONE instance per invocation and a host runs more than one
    Fabro server, so the canonical host is instance data — not host data and
    certainly not role data.
    """
    unit = _UNIT_TEMPLATE.read_text(encoding="utf-8")

    assert f"Environment={_CANONICAL_HOST_VAR}={{{{ fabro_server_canonical_host }}}}" in unit

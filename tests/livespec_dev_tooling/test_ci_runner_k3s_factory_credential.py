"""The factory credential is RENDERED by the boot converge, with the tailnet address.

`ci-runner/k3s/phase2/factory/factory-rbac.yaml` is the non-secret half of the
`factory` namespace's `sandbox-launcher` identity; the kubeconfig carrying its
bearer token is deliberately never committed. This file asserts the half that
produces it: `reconstruct/converge-ci-stack.sh` re-renders
`/etc/ci-runner/factory.kubeconfig` on the control-plane node on EVERY run, and
the committed exit-test suite beside the manifests exercises that render the way
`../gates/gates-credential-exit-tests.sh` exercises the gates one.

WHY ON EVERY RUN. The node's k3s datastore is a tmpfs, so the ServiceAccount
and its token Secret are wiped at each boot and a kubeconfig rendered once
carries a token the fresh API server has never seen — the `Unauthorized`
failure `../../observability/kueue-webhook-probe-rbac.yaml` records from
2026-09-02. A render ordered behind any condition is a credential that is
missing exactly when nobody is watching, so the render is asserted to be
UNCONDITIONAL rather than merely present.

WHY THE TAILNET ADDRESS AND NOT THE LOOPBACK DEFAULT. This credential LEAVES
the control-plane node: it is consumed on whichever host runs the Fabro server.
`render-sa-kubeconfig.sh` defaults `--server` to `https://127.0.0.1:6443`,
which is correct for an on-host caller and names the READER's own machine for
anyone else — a kubeconfig that looks valid and cannot reach a cluster. The
tailnet name is the one the API server holds a SAN for.

Work-item: `livespec-dev-tooling-sqobqv`. Plan: livespec
`factory-worker-nodes-gitops`, epic `livespec-sqvj7p`.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PHASE2 = _REPO_ROOT / "ci-runner" / "k3s" / "phase2"
_FACTORY_DIR = _PHASE2 / "factory"
_FACTORY_RBAC = _FACTORY_DIR / "factory-rbac.yaml"
_EXIT_TESTS = _FACTORY_DIR / "factory-credential-exit-tests.sh"
_GATES_EXIT_TESTS = _PHASE2 / "gates" / "gates-credential-exit-tests.sh"
_BOOT_CONVERGE = _PHASE2 / "reconstruct" / "converge-ci-stack.sh"
_RENDERER = _PHASE2 / "reconstruct" / "render-sa-kubeconfig.sh"

# The credential the converge renders, and the identity it renders it for. The
# ServiceAccount and the token Secret names are the manifest's to choose, so
# they are asserted to AGREE with it rather than spelled independently.
_RENDER_DEST = "/etc/ci-runner/factory.kubeconfig"
_SERVICE_ACCOUNT = "sandbox-launcher"
_TOKEN_SECRET = "sandbox-launcher-token"
_NAMESPACE = "factory"

# The shell variables the converge must carry, each overridable by a `CI_`
# environment variable exactly as the gates and node-status ones are, so an
# operator can re-render to a scratch path without editing the script.
_DEST_VARIABLE = "FACTORY_KUBECONFIG"
_SERVER_VARIABLE = "FACTORY_SERVER"

# The loopback the renderer defaults to. Correct for an on-host caller, and
# exactly wrong for a credential that leaves the host.
_LOOPBACK = "127.0.0.1"


def _read(*, path: Path) -> str:
    """One committed file, asserting its presence first.

    Stated as an ASSERTION rather than left to surface as a `FileNotFoundError`
    from inside a reader: a test that dies before its first assertion proves
    only that a path is missing, not what the missing thing was supposed to do.
    """
    assert path.is_file(), (
        f"{path.relative_to(_REPO_ROOT)} must exist: the factory credential is "
        f"rendered on every boot by committed code, and a render that lives only "
        f"on a host is gone at the next boot of the tmpfs datastore"
    )
    return path.read_text(encoding="utf-8")


def _render_call(*, body: str, dest_variable: str) -> str:
    """The one `render-sa-kubeconfig.sh` invocation writing `dest_variable`.

    Returned as its whole continued command — the renderer is called with
    backslash-continued arguments, so the call is every line from the
    `"${RENDER_SA_KUBECONFIG}"` opening up to the first line not ending in a
    backslash.
    """
    lines = body.splitlines()
    openings = [
        index for index, line in enumerate(lines) if line.strip() == '"${RENDER_SA_KUBECONFIG}" \\'
    ]
    calls: list[str] = []
    for start in openings:
        stop = start
        while stop < len(lines) and lines[stop].rstrip().endswith("\\"):
            stop += 1
        calls.append("\n".join(lines[start : stop + 1]))
    matching = [call for call in calls if f'--dest "${{{dest_variable}}}"' in call]
    assert len(matching) == 1, (
        f"converge-ci-stack.sh must carry exactly one render writing "
        f"${{{dest_variable}}}; found {len(matching)} among {len(calls)} renderer calls, "
        f"so this test is reading the wrong one or none at all"
    )
    return matching[0]


def test_the_boot_converge_renders_the_factory_credential_for_the_launcher_identity() -> None:
    """The render names the namespace, the token Secret and the user the manifest declares.

    Asserted against `factory-rbac.yaml` rather than against literals of its own:
    the names are that manifest's to choose, and a render that read a Secret the
    manifest does not request would wait out the renderer's 60-second token poll
    and then fail — on a boot path where the failure is a credential that is
    simply absent.
    """
    body = _read(path=_BOOT_CONVERGE)
    manifest = _read(path=_FACTORY_RBAC)
    call = _render_call(body=body, dest_variable=_DEST_VARIABLE)

    assert f"name: {_SERVICE_ACCOUNT}" in manifest
    assert f"name: {_TOKEN_SECRET}" in manifest
    assert f"--namespace {_NAMESPACE}" in call
    assert f"--secret {_TOKEN_SECRET}" in call
    assert f"--user {_SERVICE_ACCOUNT}" in call
    assert re.search(
        rf'^{_DEST_VARIABLE}="\$\{{CI_{_DEST_VARIABLE}:-{re.escape(_RENDER_DEST)}\}}"$',
        body,
        re.MULTILINE,
    ), (
        f"the converge must declare {_DEST_VARIABLE} defaulting to {_RENDER_DEST} and "
        f"overridable by CI_{_DEST_VARIABLE}, exactly as the gates and node-status "
        f"credentials are, so an operator can re-render without editing the script"
    )


def test_the_rendered_factory_credential_names_the_tailnet_api_address() -> None:
    """The credential LEAVES this host, so the loopback default must not stand.

    `render-sa-kubeconfig.sh` defaults `--server` to the loopback, which names
    the READER's own machine once the file is consumed anywhere else: a
    kubeconfig that is syntactically perfect and reaches no cluster. The address
    is the tailnet name the API server holds a SAN for, taken from the same
    variable the gates credential already resolves so there is ONE literal.
    """
    body = _read(path=_BOOT_CONVERGE)
    call = _render_call(body=body, dest_variable=_DEST_VARIABLE)
    # `.+` rather than a non-brace class: the default is allowed to be another
    # shell expansion (`${GATES_SERVER}`), which is the spelling that keeps one
    # literal for this node's tailnet address — and a class excluding `}` would
    # read that correct form as no declaration at all.
    declaration = re.search(
        rf'^{_SERVER_VARIABLE}="\$\{{CI_{_SERVER_VARIABLE}:-(?P<default>.+)\}}"$',
        body,
        re.MULTILINE,
    )

    assert f'--server "${{{_SERVER_VARIABLE}}}"' in call, (
        "the render must pass --server explicitly; omitting it takes the renderer's "
        "loopback default, which is wrong for every consumer of this credential"
    )
    assert declaration is not None, (
        f"the converge must declare {_SERVER_VARIABLE}, overridable by " f"CI_{_SERVER_VARIABLE}"
    )
    assert _LOOPBACK not in declaration["default"], (
        "the API address must not be the loopback: this credential is read on "
        "another machine, where loopback names that machine"
    )
    assert ".ts.net" in declaration["default"] or "GATES_SERVER" in declaration["default"], (
        "the API address must be the tailnet name the API server holds a SAN for — "
        "either spelled, or resolved from the gates credential's own variable so the "
        "fleet keeps ONE literal for the control-plane node's tailnet address"
    )


def test_the_factory_render_is_unconditional_and_ordered_inside_its_own_step() -> None:
    """Rendered on EVERY run, inside step 10e, after the objects it reads exist.

    UNCONDITIONAL is the load-bearing half. The ServiceAccount and its token
    Secret are wiped at every boot, so a render behind a condition — a
    file-exists guard, a `||  true`, an `if` — is a credential that is missing
    exactly after the event that invalidated the old one, and its absence raises
    nothing. Ordered AFTER the directory apply because the token Secret the
    renderer polls for is created by that apply.
    """
    body = _read(path=_BOOT_CONVERGE)
    call = _render_call(body=body, dest_variable=_DEST_VARIABLE)
    apply_at = body.find(f'kubectl apply -f "${{{_NAMESPACE.upper()}_DIR}}"')
    call_at = body.find(call)
    step_log = re.search(r'(?m)^log "(?P<step>10e\.[^"]*)"$', body)
    indent = call.splitlines()[0][: -len(call.splitlines()[0].lstrip())]

    assert step_log is not None
    assert -1 < apply_at < call_at, (
        "the render must follow the factory directory's apply: the token Secret it "
        "polls for is created by that apply, and the renderer's 60-second wait is not "
        "a substitute for ordering"
    )
    assert indent == "", (
        "the render must sit at the script's top level, not nested inside a "
        "conditional: a credential rendered only sometimes is absent exactly when a "
        "boot has just invalidated the previous one, and nothing reports it"
    )
    # The step the render belongs to must still be the LAST numbered step before
    # the informational reads, so a reader of the boot journal sees the whole
    # factory converge — objects and credential — reported under one heading.
    verify_log = body.find('log "11. Verify')
    assert -1 < call_at < verify_log


def test_the_committed_exit_tests_exercise_the_factory_render() -> None:
    """The render has the same committed, host-free proof the gates render has.

    The gates suite runs the REAL renderer against a faked `kubectl` and a faked
    `chown`, so no cluster is contacted, no credential exists, and every path
    written is inside its own scratch directory. The factory suite is asserted to
    do the same three things that suite does for the render: write a supplied
    `--server` verbatim, leave no loopback remnant behind, and still refuse an
    unknown argument — the last one because the `--server` flag these credentials
    depend on was added to a parser that must not have become permissive.
    """
    suite = _read(path=_EXIT_TESTS)
    gates_suite = _read(path=_GATES_EXIT_TESTS)

    assert _EXIT_TESTS.stat().st_mode & 0o111, (
        "the exit-test suite must be executable, like every other committed "
        "*-exit-tests.sh beside the artifacts it proves"
    )
    assert "render-sa-kubeconfig.sh" in suite, (
        "the suite must drive the REAL renderer; a suite that re-implemented the "
        "render would prove its own copy and not the code the boot runs"
    )
    for faked in ("kubectl", "chown"):
        assert faked in suite, (
            f"the suite must fake {faked}, exactly as the gates suite does: no cluster "
            f"may be contacted and it must pass as an unprivileged user"
        )
        assert faked in gates_suite
    # The IDENTITY the suite renders as, not the quoting it reaches it with: the
    # suite names these in shell variables so a rename lands in one place, and
    # pinning `--secret <literal>` here would fail a suite that is more correct
    # than the assertion.
    assert "--secret" in suite
    assert "--user" in suite
    assert _TOKEN_SECRET in suite, (
        "the suite must render the token Secret this manifest requests; a suite "
        "rendering some other Secret proves a credential the boot never produces"
    )
    assert _SERVICE_ACCOUNT in suite
    assert ".ts.net" in suite, (
        "the suite must exercise the TAILNET address this credential is rendered "
        "with, which is the one property distinguishing it from the on-host probe"
    )
    assert _LOOPBACK in suite, (
        "the suite must assert the loopback default does NOT leak into the rendered "
        "file, which is the gates suite's arm B and the failure mode that makes a "
        "credential look valid and reach nothing"
    )


def test_the_renderer_the_exit_tests_drive_still_refuses_an_unknown_argument() -> None:
    """The parser both credentials depend on is strict, and the suite checks it.

    `--server` exists only because a kubeconfig that leaves the host needs it.
    Adding a flag to an argument parser is the moment a parser becomes
    permissive, and a permissive one accepts a MISSPELLED `--server` silently —
    leaving the loopback default in a credential nobody can use and no error
    anywhere. The renderer's refusal is asserted here, and the suite's own arm
    for it is asserted above.
    """
    renderer = _read(path=_RENDERER)
    suite = _read(path=_EXIT_TESTS)

    assert "FATAL: unknown argument" in renderer
    assert "--bogus" in suite, (
        "the suite must drive the renderer with an unknown argument and require a "
        "non-zero exit, which is the gates suite's arm C"
    )

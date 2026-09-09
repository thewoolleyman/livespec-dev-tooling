"""Consumer-tier: a check attempts forbidden network I/O.

Covers the `SPECIFICATION/scenarios.md` scenario "a check attempts
forbidden network I/O" — the `no-network-io` gate that asserts every
check stays within the local-filesystem + project-local-subprocess
envelope — and the `SPECIFICATION/constraints.md` section "No network I/O"
that scenario enforces.

The scenario notes the gate is "sketch only — the gate may itself be
tested by a sandboxed firewall fixture or by AST inspection." Both paths
are taken here, because they answer different halves of the constraint:

- The consumer-observable invariant, by AST: EVERY shipped check module
  under `livespec_dev_tooling/checks/` is free of network-library imports,
  so a consumer's `just check` is deterministic against the working tree
  alone regardless of network availability.
- The gate's detection logic, by AST: a fixture check module that imports a
  forbidden network library IS detected by the same scan — proving the gate
  would fail the build for a network-touching check.
- The constraint's REASON, by execution: a shipped check is driven
  end-to-end with every `socket` constructor replaced by a double that
  refuses, and still exits `0`. An import scan can only say a module names
  no network library; only running the check with the network stack
  removed shows the EXECUTION PATH reaches no endpoint — through a
  helper, through a lazily-imported module, or through anything the AST
  never sees. That is the determinism guarantee the constraint exists for,
  and the constraint's own second paragraph is what makes this a check-tier
  probe rather than a repository-wide one: the ban is scoped to Python
  check modules precisely because their determinism is load-bearing for
  `just check`, while the workflow surface may reach the network freely.

The AST paths never execute the modules they read, consistent with the
constraint they guard; the execution path runs one check whose whole world
is the working directory.
"""

from __future__ import annotations

import ast
import importlib
import socket
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CHECKS_DIR = _REPO_ROOT / "livespec_dev_tooling" / "checks"

# Top-level package names whose import implies network I/O (sockets,
# HTTP(S) clients, mail/FTP/telnet, async network stacks). Reaching a
# remote endpoint or opening a socket is forbidden in check modules per
# `constraints.md` section "No network I/O".
_FORBIDDEN_NETWORK_ROOTS: frozenset[str] = frozenset(
    {
        "socket",
        "ssl",
        "urllib",
        "http",
        "ftplib",
        "telnetlib",
        "smtplib",
        "poplib",
        "imaplib",
        "requests",
        "httpx",
        "aiohttp",
        "websockets",
        "xmlrpc",
    }
)

# The shipped check driven with the network stack removed. It reads its whole
# world from the working directory (a spec tree plus the coverage registry) and
# needs no role-key configuration, so a two-file fixture is a complete input —
# the same reason `test_two_consumption_surfaces` drives this module.
_DRIVEN_CHECK = "livespec_dev_tooling.checks.heading_coverage"
_FIXTURE_HEADING = "## Project intent"
_FIXTURE_TEST_ID = "tests.fixture.test_intent.test_intent"

# Every `socket` entry point a network reach would pass through, each replaced
# by the refusing double below. Naming the constructors rather than one of them
# is what closes the "it used a different door" gap.
_SOCKET_CONSTRUCTORS = ("socket", "create_connection", "getaddrinfo", "socketpair")

_NETWORK_REACHED = "a check reached the network stack"


def _refuse_network(*_args: object, **_kwargs: object) -> None:
    """Stand in for every `socket` entry point: reaching the network is a defect.

    Raises rather than returning a dud object so a reach surfaces at the call
    site with the reason attached, instead of failing later as an unrelated
    `AttributeError` on whatever the caller expected back.
    """
    raise RuntimeError(_NETWORK_REACHED)


def _write_fixture_tree(*, root: Path) -> None:
    """A minimal consumer tree: one spec heading plus its coverage registry."""
    spec_dir = root / "SPECIFICATION"
    spec_dir.mkdir(parents=True, exist_ok=True)
    _ = spec_dir.joinpath("spec.md").write_text(
        f"# Fixture spec\n\n{_FIXTURE_HEADING}\n\nProse.\n", encoding="utf-8"
    )
    tests_dir = root / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    _ = tests_dir.joinpath("heading-coverage.json").write_text(
        '[{"spec_root": "SPECIFICATION", "spec_file": "spec.md", '
        f'"heading": "{_FIXTURE_HEADING}", "test": "{_FIXTURE_TEST_ID}"}}]',
        encoding="utf-8",
    )


def _imported_roots(*, source: str) -> set[str]:
    """The set of top-level module roots imported by `source` (via AST)."""
    tree = ast.parse(source)
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom) and node.module is not None and node.level == 0:
            roots.add(node.module.split(".", 1)[0])
    return roots


def _network_imports(*, source: str) -> set[str]:
    return _imported_roots(source=source) & _FORBIDDEN_NETWORK_ROOTS


def test_no_shipped_check_imports_a_network_library() -> None:
    """Every shipped check module is free of forbidden network-library imports.

    The consumer-observable determinism guarantee: a consumer's `just check`
    never depends on network availability.
    """
    # Map each shipped module to its set of forbidden network-library roots
    # (almost always empty). Asserting the union across all modules is empty
    # avoids a conditionally-dead `if found:` branch while still surfacing the
    # full per-module mapping in the failure message when the invariant breaks.
    per_module = {
        module_path.name: _network_imports(source=module_path.read_text(encoding="utf-8"))
        for module_path in sorted(_CHECKS_DIR.glob("*.py"))
    }
    all_network_roots: set[str] = set().union(*per_module.values())

    assert not all_network_roots, (
        f"no check module may import a network library "
        f'(constraints.md §"No network I/O"); per-module imports={per_module}'
    )


def test_gate_detects_a_network_touching_fixture_check(*, tmp_path: Path) -> None:
    """A fixture check that imports a network library IS caught by the gate's scan.

    Proves the gate would fail the build for a network-touching check — the
    scenario's "the gate fails the build" outcome.
    """
    fixture = tmp_path / "naughty_check.py"
    fixture.write_text(
        "from __future__ import annotations\n"
        "\n"
        "import urllib.request\n"
        "\n"
        "\n"
        "def main() -> int:\n"
        '    urllib.request.urlopen("https://example.com")\n'
        "    return 0\n",
        encoding="utf-8",
    )

    found = _network_imports(source=fixture.read_text(encoding="utf-8"))

    assert "urllib" in found, (
        f"the no-network-io scan must catch a check importing `urllib`; " f"found={found}"
    )


def test_a_shipped_check_passes_with_the_network_stack_disabled(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A shipped check reaches its verdict with every `socket` entry point refusing.

    The constraint's stated purpose: "every check is deterministic against the
    consuming repo's working tree alone, regardless of network availability".
    A consumer running `just check` offline gets the same verdict, and this is
    the leg of that claim the import scan cannot reach — a network call made
    through a helper or a lazily-imported module names no forbidden root in the
    check module's own AST.
    """
    module = importlib.import_module(_DRIVEN_CHECK)
    _write_fixture_tree(root=tmp_path)
    for constructor in _SOCKET_CONSTRUCTORS:
        monkeypatch.setattr(socket, constructor, _refuse_network)
    monkeypatch.chdir(tmp_path)

    returncode = module.main()

    captured = capsys.readouterr()
    assert returncode == 0, (
        f"a shipped check must reach its verdict with no network stack; "
        f"returncode={returncode} stderr={captured.err!r}"
    )
    # The double is asserted LIVE at the end rather than trusted: a
    # `monkeypatch.setattr` that silently bound nothing would make the run above
    # an ordinary networked one reported as an offline pass.
    with pytest.raises(RuntimeError, match=_NETWORK_REACHED):
        _ = socket.socket()

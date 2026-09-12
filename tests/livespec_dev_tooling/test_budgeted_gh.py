"""Tests for `livespec_dev_tooling/budgeted_gh.py` and the retrofit it landed.

Two halves, and the second is the point of the work-item
(livespec-dev-tooling-z69s, livespec core epic livespec-httc):

1. The boundary itself — `gh_read` answers in the `CompletedProcess`
   vocabulary its callers already read, passes the argument tail through
   unchanged, and turns every read it could not take (absent binary,
   expired timeout, a rate limit the client measured) into a non-zero
   read rather than an exception or a fabricated answer.

2. THE CONTROLS over the enforcement-suite files the retrofit converted.
   The NEGATIVE control parses each file and asserts it contains no
   direct `gh` call site at all; the POSITIVE control asserts each file
   reaches GitHub through `gh_read`, with the site count the inventory
   names, and that the name it imports IS the budgeted boundary rather
   than a same-named local. The two together are what "routes through the
   client" means mechanically, and neither can be satisfied by a file
   that kept a spawn.

   `branch_protection_alignment.py` carries ZERO of either: its forge
   reads moved into the private `_branch_protection_api` split-out
   (R4.S6, livespec-dev-tooling-ul61) before this retrofit, and that is
   the file the conversion had to reach. Both are listed below so the
   negative control covers the named file as well as its successor.

The strongest positive control here is not an AST count but the DURABLE
BUDGET SIGNAL: the vendored transport appends one JSONL row per read it
could MEASURE, and only the budgeted transport writes it. A site whose
read produced a row demonstrably went through the client. Two sites are
driven that way end-to-end below, with a fake `gh` that echoes
`x-ratelimit-*` headers the way `gh` does under `GH_DEBUG=api`.
"""

from __future__ import annotations

import ast
import importlib.metadata
import inspect
import json
import os
from pathlib import Path

import pytest

from livespec_dev_tooling import budgeted_gh
from livespec_dev_tooling.agent_hooks import subagent_stop_guard
from livespec_dev_tooling.budgeted_gh import GhRead, gh_read
from livespec_dev_tooling.checks import _branch_protection_api, master_ci_green
from livespec_dev_tooling.checks._branch_protection_api import _default_branch_from_api
from livespec_dev_tooling.checks.master_ci_green import _gh_has_stored_credential

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SIGNAL_PATH_ENV = "LIVESPEC_GITHUB_BUDGET_LOG"
_SUBPROCESS_SPAWNERS = frozenset({"run", "Popen", "call", "check_call", "check_output"})

# The retrofitted files, each with the number of budgeted reads it is
# expected to issue. MEASURED from the tree, not projected: the
# work-item's 2026-08-08 inventory predates both the
# `_branch_protection_api` split-out and the `enforce_admins`
# sub-endpoint read (livespec-dev-tooling-65c), so the count there is
# three rather than the two it names.
_RETROFITTED_SITES: dict[str, int] = {
    "livespec_dev_tooling/checks/branch_protection_alignment.py": 0,
    "livespec_dev_tooling/checks/_branch_protection_api.py": 3,
    "livespec_dev_tooling/checks/master_ci_green.py": 2,
    "livespec_dev_tooling/agent_hooks/subagent_stop_guard.py": 1,
}
_BUDGETED_MODULE = "livespec_dev_tooling.budgeted_gh"
# The rate-limit headers `gh` echoes on a measured response. `remaining`
# is deliberately non-zero in the ordinary fixtures: a measured budget
# with room left must not change any answer.
_MEASURED_HEADERS = (
    "x-ratelimit-limit: 5000",
    "x-ratelimit-remaining: 4998",
    "x-ratelimit-used: 2",
    "x-ratelimit-reset: 1789180000",
    "x-ratelimit-resource: core",
)
_EXHAUSTED_HEADERS = (
    "x-ratelimit-limit: 5000",
    "x-ratelimit-remaining: 0",
    "x-ratelimit-used: 5000",
    "x-ratelimit-reset: 1789180000",
    "x-ratelimit-resource: core",
)


def _install_fake_gh(
    *,
    tmp_path: Path,
    stdout: str = "{}",
    stderr_lines: tuple[str, ...] = (),
    returncode: int = 0,
) -> str:
    """Install a fake `gh` at `tmp_path/bin`, returning a PATH that finds it.

    The stub records each invocation's argument tail in `bin/gh.argv` (one
    line per call) so a test can assert the argv the transport built, and
    its `pwd` in `bin/gh.cwd` so the `cwd` passthrough is observable.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    gh_path = bin_dir / "gh"
    stderr_block = (
        ""
        if not stderr_lines
        else "cat >&2 <<'STUB_ERR_EOF'\n" + "\n".join(stderr_lines) + "\nSTUB_ERR_EOF\n"
    )
    script = "\n".join(
        [
            "#!/bin/sh",
            f"printf '%s\\n' \"$*\" >> '{bin_dir}/gh.argv'",
            f"pwd >> '{bin_dir}/gh.cwd'",
            f"cat <<'STUB_EOF'\n{stdout}\nSTUB_EOF",
            f"{stderr_block}exit {returncode}",
            "",
        ]
    )
    _ = gh_path.write_text(script, encoding="utf-8")
    gh_path.chmod(0o755)
    return f"{bin_dir}{os.pathsep}{os.environ['PATH']}"


def _signal_rows(*, path: Path) -> list[dict[str, object]]:
    """Every durable budget-signal row written so far, oldest first.

    Reads the path unguarded on purpose: a caller reaches here only after
    a read it expected to be MEASURED, so an absent file is the very
    failure these tests exist to catch and must surface as one rather than
    as an empty list that compares unequal three lines later.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line]


def _parsed_site(*, relative_path: str) -> ast.Module:
    return ast.parse((_REPO_ROOT / relative_path).read_text(encoding="utf-8"))


def _literal_program(*, node: ast.expr) -> str | None:
    """The program a literal command names, when it names one literally.

    Reads the list/tuple argv form (`["gh", "api", path]`), the single
    string form a `shell=True` spawn would take, and the f-string form of
    that same single string — because "no direct `gh` call site" has to
    mean all three.
    """
    if isinstance(node, ast.List | ast.Tuple):
        head = node.elts[0] if node.elts else None
        if isinstance(head, ast.Constant) and isinstance(head.value, str):
            return head.value
        return None
    if isinstance(node, ast.JoinedStr):
        head = node.values[0] if node.values else None
        return _literal_program(node=head) if isinstance(head, ast.Constant) else None
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.split(" ")[0] or None
    return None


def _is_subprocess_spawn(*, node: ast.Call) -> bool:
    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id == "subprocess"
        and func.attr in _SUBPROCESS_SPAWNERS
    )


def _direct_gh_call_lines(*, tree: ast.Module) -> list[int]:
    """Line numbers of every direct `gh` spawn in one parsed module.

    Two detectors, because a direct call site has two shapes. An ARGV
    LITERAL whose first element is `gh` is counted wherever it appears,
    not only inside the spawn — building the list one line up and passing
    it on is exactly how `fleet/_gh_runner.py` spells the same thing, and
    a control that only watched the spawn would be satisfied by that move.
    A `subprocess.*` call whose first positional argument names `gh` as a
    string covers the `shell=True` spelling, where there is no list to
    find. `shutil.which("gh")` is NEITHER: it is a presence probe that
    reaches no forge, so a bare `"gh"` constant outside a spawn's argv
    position is deliberately not a site.
    """
    lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.List | ast.Tuple) and _literal_program(node=node) == "gh":
            lines.append(node.lineno)
        if (
            isinstance(node, ast.Call)
            and _is_subprocess_spawn(node=node)
            and node.args
            and _literal_program(node=node.args[0]) == "gh"
        ):
            lines.append(node.lineno)
    return sorted(set(lines))


def _gh_read_call_lines(*, tree: ast.Module) -> list[int]:
    """Line numbers of every `gh_read(...)` call in one parsed module."""
    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "gh_read"
    )


def _imports_budgeted_gh_read(*, tree: ast.Module) -> bool:
    """True when the module imports `gh_read` from the budgeted boundary."""
    return any(
        isinstance(node, ast.ImportFrom)
        and node.module == _BUDGETED_MODULE
        and any(alias.name == "gh_read" for alias in node.names)
        for node in ast.walk(tree)
    )


# ---------------------------------------------------------------------------
# NEGATIVE CONTROL — no direct `gh` call site survives in the retrofitted files.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("relative_path", sorted(_RETROFITTED_SITES))
def test_retrofitted_file_has_no_direct_gh_call_site(relative_path: str) -> None:
    found = _direct_gh_call_lines(tree=_parsed_site(relative_path=relative_path))
    assert found == [], f"{relative_path} still spawns gh directly at line(s) {found}"


def test_the_negative_control_detects_a_direct_gh_call_site() -> None:
    """The control's own positive control: it must convict a real spawn.

    A detector nobody ever saw convict is indistinguishable from one that
    matches nothing, and the assertion above is the kind that passes for
    free if the walk is wrong. `fleet/_gh_runner.py` is the untouched
    fleet seam this retrofit deliberately left out of scope (its pacing
    and backoff schedule are measured and caller-owned), so it is a REAL
    direct call site standing in the same tree — the honest specimen.
    """
    seam = _parsed_site(relative_path="livespec_dev_tooling/fleet/_gh_runner.py")
    assert _direct_gh_call_lines(tree=seam) != []
    assert _direct_gh_call_lines(tree=ast.parse('subprocess.run("gh api repos/o/r", shell=True)'))
    assert _direct_gh_call_lines(tree=ast.parse('subprocess.run(f"gh api repos/{r}", shell=True)'))
    # ...and it must ACQUIT a command whose program is not literally `gh`,
    # or "zero direct sites" would be a claim about nothing.
    assert (
        _direct_gh_call_lines(tree=ast.parse('subprocess.run(f"{binary} api", shell=True)')) == []
    )
    assert _direct_gh_call_lines(tree=ast.parse('shutil.which("gh")')) == []


# ---------------------------------------------------------------------------
# POSITIVE CONTROL — every one of those reads goes through the budgeted client.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("relative_path", "expected"), sorted(_RETROFITTED_SITES.items()))
def test_retrofitted_file_routes_its_reads_through_the_budgeted_client(
    relative_path: str, expected: int
) -> None:
    tree = _parsed_site(relative_path=relative_path)
    assert len(_gh_read_call_lines(tree=tree)) == expected
    assert _imports_budgeted_gh_read(tree=tree) is (expected > 0)


def test_each_site_module_binds_the_real_budgeted_boundary() -> None:
    """The imported `gh_read` IS `budgeted_gh.gh_read`, not a same-named local."""
    assert _branch_protection_api.gh_read is gh_read
    assert master_ci_green.gh_read is gh_read
    assert subagent_stop_guard.gh_read is gh_read


# ---------------------------------------------------------------------------
# The boundary itself.
# ---------------------------------------------------------------------------


def test_gh_read_passes_the_argument_tail_through_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", _install_fake_gh(tmp_path=tmp_path, stdout='{"ok": true}'))
    answer = gh_read(args=["api", "repos/test-owner/test-repo"])
    assert answer == GhRead(returncode=0, stdout='{"ok": true}\n', stderr="")
    recorded = (tmp_path / "bin" / "gh.argv").read_text(encoding="utf-8").splitlines()
    assert recorded == ["api repos/test-owner/test-repo"]


def test_gh_read_reports_a_non_zero_exit_as_the_answer_it_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `gh` that RAN and said no stays on the ordinary track, streams intact."""
    monkeypatch.setenv(
        "PATH",
        _install_fake_gh(
            tmp_path=tmp_path,
            stdout='{"message": "Branch not protected"}',
            stderr_lines=("gh: Branch not protected (HTTP 404)",),
            returncode=1,
        ),
    )
    answer = gh_read(args=["api", "repos/o/r/branches/master/protection"])
    assert answer.returncode == 1
    assert "Branch not protected" in answer.stdout
    assert "(HTTP 404)" in answer.stderr


def test_gh_read_runs_in_the_requested_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    monkeypatch.setenv("PATH", _install_fake_gh(tmp_path=tmp_path))
    _ = gh_read(args=["pr", "view", "feat/x"], cwd=worktree)
    recorded = (tmp_path / "bin" / "gh.cwd").read_text(encoding="utf-8").strip()
    assert Path(recorded).resolve() == worktree.resolve()


def test_gh_read_reports_an_absent_binary_as_a_read_that_did_not_happen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", str(empty_bin))
    answer = gh_read(args=["api", "repos/o/r"])
    assert answer.returncode == 127
    assert answer.stdout == ""
    assert answer.stderr != ""


def test_gh_read_reports_an_expired_timeout_as_a_read_that_did_not_happen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    slow_gh = bin_dir / "gh"
    _ = slow_gh.write_text("#!/bin/sh\nsleep 5\n", encoding="utf-8")
    slow_gh.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    answer = gh_read(args=["api", "repos/o/r"], timeout=0.2)
    assert answer.returncode == 127
    assert answer.stdout == ""
    assert answer.stderr != ""


def test_gh_read_reports_a_measured_rate_limit_as_a_read_that_did_not_happen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refusal the CLIENT made — the branch only a budgeted read can reach."""
    monkeypatch.setenv(_SIGNAL_PATH_ENV, str(tmp_path / "budget.jsonl"))
    monkeypatch.setenv(
        "PATH",
        _install_fake_gh(
            tmp_path=tmp_path,
            stdout="",
            stderr_lines=(*_EXHAUSTED_HEADERS, "gh: API rate limit exceeded (HTTP 403)"),
            returncode=1,
        ),
    )
    answer = gh_read(args=["api", "repos/o/r"])
    assert answer.returncode == 1
    assert answer.stdout == ""
    assert "primary_exhaustion" in answer.stderr


# ---------------------------------------------------------------------------
# The durable budget signal — the non-forgeable proof a site used the client.
# ---------------------------------------------------------------------------


def test_the_credential_probe_read_is_recorded_on_the_budget_signal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    signal = tmp_path / "budget.jsonl"
    monkeypatch.setenv(_SIGNAL_PATH_ENV, str(signal))
    monkeypatch.setenv(
        "PATH",
        _install_fake_gh(tmp_path=tmp_path, stdout="gho_token", stderr_lines=_MEASURED_HEADERS),
    )
    assert _gh_has_stored_credential() is True
    rows = _signal_rows(path=signal)
    assert [row["argv"] for row in rows] == ["gh auth token"]
    assert rows[0]["remaining"] == 4998
    # The token is the probe's stdout and must not reach the signal.
    assert "gho_token" not in signal.read_text(encoding="utf-8")


def test_the_default_branch_read_is_recorded_on_the_budget_signal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    signal = tmp_path / "budget.jsonl"
    monkeypatch.setenv(_SIGNAL_PATH_ENV, str(signal))
    monkeypatch.setenv(
        "PATH",
        _install_fake_gh(
            tmp_path=tmp_path,
            stdout='{"default_branch": "main"}',
            stderr_lines=_MEASURED_HEADERS,
        ),
    )
    resolved = _default_branch_from_api(owner_repo="test-owner/test-repo")
    assert resolved == "main"
    assert [row["argv"] for row in _signal_rows(path=signal)] == [
        "gh api repos/test-owner/test-repo"
    ]


# ---------------------------------------------------------------------------
# The client is VENDORED, per the retrofit's prerequisite — not a dependency.
# ---------------------------------------------------------------------------


def test_the_budgeted_client_is_vendored_rather_than_a_runtime_dependency() -> None:
    vendored = _REPO_ROOT / "livespec_dev_tooling" / "_vendor" / "livespec_runtime"
    assert (vendored / "github_budget.py").is_file()
    client_source = Path(inspect.getfile(budgeted_gh.GithubBudgetedClient))
    assert client_source.is_relative_to(vendored)
    installed = {
        distribution.metadata["Name"] for distribution in importlib.metadata.distributions()
    }
    assert "livespec-runtime" not in installed

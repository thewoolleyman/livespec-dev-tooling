"""Consumer-tier: a gate Job's PyPI-cache lock routing leaves the change set as pushed.

The two v210 scenarios of `SPECIFICATION/scenarios.md` that follow the
flake-retry scenarios, for the `SPECIFICATION/non-functional-requirements.md`
sentence on runner-pool build cache tiers that says a gate Job that routes a
repository's locked artifacts through a host-served cache leaves every tracked
file unmodified as git compares the Job's working tree with its index and with
`HEAD` (livespec-dev-tooling-o4hkgh).

The defect this closes: the gate Job template rewrote every `uv.lock` IN PLACE
to point at the pool's PyPI files proxy, so `uv.lock` read as an unstaged
change in every delegated gate, and the flake-retry plugin withheld every retry
of the session as "a non-version-only pyproject.toml or uv.lock change". The
version-only release exception read the proxied bytes from disk too, so even a
release commit's lock was judged as more than a version bump.

Driven here as a gate Job meets it, with nothing stubbed that the claim rests
on:

- the gate container's script is RENDERED by the real renderer and run under
  bash, in a REAL git checkout whose `origin/master` is the base and whose
  detached `HEAD` is the pushed commit, exactly as the fetch-tree init
  container leaves `/workspace`;
- the pool's PyPI files proxy is a local stand-in that serves the locked
  artifact, so the script's lock-routing step really runs;
- the recipe is a stub `just` that runs a REAL pytest session in that checkout
  with the flake-retry plugin, and records `git diff <base> -- uv.lock` as the
  Job sees it when the checks run.

Only `uv` is a stub: it records the lock it was asked to sync and fetches
nothing. The nested pytest is spawned by bash, not by this module, and its
environment carries no coverage start-up variable, so it does not
self-instrument (the `tests_no_subprocess_spawn` concern).
"""

from __future__ import annotations

import functools
import http.server
import os
import subprocess
import sys
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RENDERER = _REPO_ROOT / "ci-runner" / "k3s" / "phase2" / "gates" / "render-gate-job.sh"
_EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
_SCRUB_PREFIXES = ("GIT_", "COVERAGE_", "COV_CORE_", "GITHUB_")
_GIT_IDENTITY = (
    "-c",
    "user.email=gate-fixture@example.invalid",
    "-c",
    "user.name=gate-fixture",
    "-c",
    "commit.gpgsign=false",
    "-c",
    "core.hooksPath=/dev/null",
)
_LOCKED_ARTIFACT = "/packages/good/good-1.0-py3-none-any.whl"
_FLAKY_TEST = (
    "from pathlib import Path\n"
    "\n"
    "\n"
    "def test_flaky():\n"
    "    marker = Path(__file__).with_name('seen')\n"
    "    if not marker.exists():\n"
    "        marker.write_text('1')\n"
    "        raise AssertionError('first attempt fails')\n"
)
# Committed into the base, so the change set never contains it: it only takes
# the minute out of the retry delay for this throwaway session.
_NO_DELAY_CONFTEST = "import livespec_dev_tooling.flake_retry as flake_retry\n\nflake_retry.RETRY_DELAY_SECONDS = 0\n"
_PYPROJECT = "[project]\nname = 'retry-fixture'\nversion = '{version}'\n"
# A lock whose third-party artifact carries the absolute PyPI file URL a real
# frozen lock carries, so the gate's lock routing has a URL to send through the
# stand-in proxy. Only the repository's own package version differs between
# the base and a release.
_UV_LOCK = (
    "version = 1\n"
    "\n"
    "[[package]]\n"
    "name = 'retry-fixture'\n"
    "version = '{version}'\n"
    "\n"
    "[[package]]\n"
    "name = 'good'\n"
    "version = '1.0'\n"
    'wheels = [{{ url = "https://files.pythonhosted.org/packages/good/good-1.0-py3-none-any.whl", '
    'hash = "sha256:good" }}]\n'
)
# The fixture consumer's CI, from which the renderer reads the gate image.
_CI_WORKFLOW = (
    "jobs:\n  one:\n    runs-on: self-hosted\n    container:\n"
    "      image: ghcr.io/example/sandbox:python-v1.11.1\n"
)
# The recipe the Job runs: what a check reading the change set sees, then a
# real pytest session under the flake-retry plugin.
_JUST_STUB = """#!/usr/bin/env bash
[ "${1:-}" = "--show" ] && exit 0
git diff "$(git merge-base HEAD origin/master)" -- uv.lock > "${RECIPE_LOCK_DIFF}"
exec "${GATE_TEST_PYTHON}" -m pytest -q -p no:cacheprovider -p no:livespec_flake_retry \\
  -p livespec_dev_tooling.flake_retry test_flaky.py
"""
_UV_STUB = """#!/usr/bin/env bash
if [ "${1:-}" = "sync" ]; then
  cp uv.lock "${UV_SYNCED_LOCK}"
fi
exit 0
"""


@pytest.fixture
def stand_in_proxy(*, tmp_path: Path) -> Iterator[str]:
    """Serve the locked artifact as the pool's PyPI files proxy would."""
    root = tmp_path / "proxy"
    artifact = root / _LOCKED_ARTIFACT.lstrip("/")
    artifact.parent.mkdir(parents=True)
    _ = artifact.write_bytes(b"wheel\n")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def _scrubbed_env() -> dict[str, str]:
    """This process's environment without git-hook, coverage and Actions variables."""
    return {k: v for k, v in os.environ.items() if not k.startswith(_SCRUB_PREFIXES)}


def _git(*, repo: Path, args: tuple[str, ...]) -> str:
    completed = subprocess.run(
        ["git", *_GIT_IDENTITY, *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=True,
        env=_scrubbed_env(),
    )
    return completed.stdout


def _pushed_checkout(*, root: Path, release: bool) -> tuple[Path, str]:
    """The Job's `/workspace`: `origin/master` at the base, a detached pushed `HEAD`.

    The pushed commit is a version-only release (`pyproject.toml` and the
    repository's own `uv.lock` package version) when `release`, and otherwise
    an unrelated `README.md` change that touches neither file. Returns the
    checkout and the base commit.
    """
    repo = root / "workspace"
    repo.mkdir()
    _ = _git(repo=repo, args=("init", "--quiet"))
    _ = (repo / "test_flaky.py").write_text(_FLAKY_TEST, encoding="utf-8")
    _ = (repo / "conftest.py").write_text(_NO_DELAY_CONFTEST, encoding="utf-8")
    _ = (repo / ".gitignore").write_text("seen\ntmp/\n__pycache__/\n", encoding="utf-8")
    _ = (repo / "pyproject.toml").write_text(_PYPROJECT.format(version="0.1.0"), encoding="utf-8")
    _ = (repo / "uv.lock").write_text(_UV_LOCK.format(version="0.1.0"), encoding="utf-8")
    _ = (repo / "README.md").write_text("base\n", encoding="utf-8")
    _ = _git(repo=repo, args=("add", "-A"))
    _ = _git(repo=repo, args=("commit", "--quiet", "-m", "base"))
    base = _git(repo=repo, args=("rev-parse", "HEAD")).strip()
    _ = _git(repo=repo, args=("update-ref", "refs/remotes/origin/master", base))
    version = "0.1.1" if release else "0.1.0"
    readme = "base\n" if release else "pushed\n"
    _ = (repo / "pyproject.toml").write_text(_PYPROJECT.format(version=version), encoding="utf-8")
    _ = (repo / "uv.lock").write_text(_UV_LOCK.format(version=version), encoding="utf-8")
    _ = (repo / "README.md").write_text(readme, encoding="utf-8")
    _ = _git(repo=repo, args=("commit", "--quiet", "-am", "pushed"))
    _ = _git(repo=repo, args=("checkout", "--quiet", "--detach", "HEAD"))
    return repo, base


def _gate_script(*, consumer: Path) -> tuple[str, dict[str, str]]:
    """Render the real gate Job for a fixture consumer; return its script and literal env."""
    workflow = consumer / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    _ = workflow.write_text(_CI_WORKFLOW, encoding="utf-8")
    rendered = subprocess.run(
        [
            str(_RENDERER),
            "--repo-root",
            str(consumer),
            "--tree-hash",
            _EMPTY_TREE,
            "--check-suite",
            "verify",
        ],
        cwd=str(consumer),
        capture_output=True,
        text=True,
        check=True,
        env=_scrubbed_env(),
    )
    job = next(doc for doc in yaml.safe_load_all(rendered.stdout) if doc)
    gate = next(c for c in job["spec"]["template"]["spec"]["containers"] if c["name"] == "gate")
    literal = {entry["name"]: str(entry["value"]) for entry in gate["env"] if "value" in entry}
    return str(gate["args"][-1]), literal


def _run_the_gate_job(*, tmp_path: Path, workspace: Path, proxy: str) -> tuple[int, str]:
    """Run the rendered gate script in `workspace`; return its exit status and its output."""
    script, literal = _gate_script(consumer=tmp_path / "consumer")
    stubs = tmp_path / "pod-bin"
    stubs.mkdir()
    for name, body in (("just", _JUST_STUB), ("uv", _UV_STUB)):
        _ = (stubs / name).write_text(body, encoding="utf-8")
        (stubs / name).chmod(0o755)
    _ = (tmp_path / "gate.sh").write_text(script, encoding="utf-8")
    env = _scrubbed_env()
    env.update(literal)
    _ = env.pop("LIVESPEC_SIBLING_CLONES_ROOT", None)
    env.update(
        {
            "PATH": f"{stubs}{os.pathsep}{env['PATH']}",
            "PYPI_FILES_PROXY": proxy,
            "UV_CACHE_DIR": str(tmp_path / "warm" / "uv"),
            "GATE_TEST_PYTHON": sys.executable,
            "RECIPE_LOCK_DIFF": str(tmp_path / "recipe-lock.diff"),
            "UV_SYNCED_LOCK": str(tmp_path / "synced-uv.lock"),
        }
    )
    (tmp_path / "warm" / "uv").mkdir(parents=True)
    _ = (tmp_path / "recipe-lock.diff").write_text("<the recipe never ran>", encoding="utf-8")
    _ = (tmp_path / "synced-uv.lock").write_text("<no lock was synced>", encoding="utf-8")
    completed = subprocess.run(
        ["bash", str(tmp_path / "gate.sh")],
        cwd=str(workspace),
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    return completed.returncode, completed.stdout + completed.stderr


@pytest.mark.integration
def test_a_gate_job_routing_locked_artifacts_through_the_cache_still_retries_an_untouched_test(
    *, tmp_path: Path, stand_in_proxy: str
) -> None:
    """Scenario: ... routes locked artifacts through the pool's cache still retries an untouched failing test.

    Given a pushed tree that changes neither `pyproject.toml` nor any `uv.lock`,
    when the Job routes its locked artifacts through the stand-in proxy and runs
    the tests, the change set the checks read is the pushed tree's and the
    failing test the change does not touch is re-run.
    """
    workspace, base = _pushed_checkout(root=tmp_path, release=False)

    status, output = _run_the_gate_job(tmp_path=tmp_path, workspace=workspace, proxy=stand_in_proxy)

    synced = (tmp_path / "synced-uv.lock").read_text(encoding="utf-8")
    facts = {
        "the gate passed": status == 0,
        "the lock was routed through the stand-in proxy": f"{stand_in_proxy}{_LOCKED_ARTIFACT}"
        in synced,
        "the untouched failing test was re-run and passed": "1 passed, 1 rerun" in output,
        "no retry was withheld": "FLAKE-RETRY-WITHHELD" not in output,
        "uv.lock is not in the Job's change set": (tmp_path / "recipe-lock.diff").read_text(
            encoding="utf-8"
        )
        == "",
        "the checkout is still the pushed tree": _git(
            repo=workspace, args=("status", "--porcelain")
        )
        == "",
        "the change set is the pushed tree's": _git(
            repo=workspace, args=("diff", "--name-only", base)
        )
        == "README.md\n",
    }
    assert all(facts.values()), (facts, output)


@pytest.mark.integration
def test_a_gate_job_routing_locked_artifacts_through_the_cache_still_reports_a_pushed_lock_change(
    *, tmp_path: Path, stand_in_proxy: str
) -> None:
    """Scenario: ... routes locked artifacts through the pool's cache still reports a pushed lockfile change.

    Given a pushed tree whose change is a version-only release of `uv.lock` and
    `pyproject.toml`, plus a failing test the change does not touch, when the
    Job routes its locked artifacts through the stand-in proxy, the Job's change
    set still lists `uv.lock` with the pushed tree's own bytes: `git diff <base>
    -- uv.lock` in the Job equals the pushed diff, so the release still reads as
    version-only and the untouched failing test is retried.
    """
    workspace, base = _pushed_checkout(root=tmp_path, release=True)
    pushed_diff = _git(repo=workspace, args=("diff", base, "HEAD", "--", "uv.lock"))

    status, output = _run_the_gate_job(tmp_path=tmp_path, workspace=workspace, proxy=stand_in_proxy)

    synced = (tmp_path / "synced-uv.lock").read_text(encoding="utf-8")
    job_diff = (tmp_path / "recipe-lock.diff").read_text(encoding="utf-8")
    facts = {
        "the gate passed": status == 0,
        "the lock was routed through the stand-in proxy": f"{stand_in_proxy}{_LOCKED_ARTIFACT}"
        in synced,
        "the pushed diff is a lock change": "+version = '0.1.1'" in pushed_diff,
        "the Job's uv.lock diff is the pushed diff": job_diff == pushed_diff,
        "the version-only release kept the retry": "1 passed, 1 rerun" in output,
        "no retry was withheld": "FLAKE-RETRY-WITHHELD" not in output,
    }
    assert all(facts.values()), (facts, output)

"""Outside-in tests for `livespec_dev_tooling/vendor_update.py`.

`vendor_update` is the maintainer-only re-vendoring tool: invoked as
`python -m livespec_dev_tooling.vendor_update <lib>`, it reads the
governed project's `.vendor.jsonc`, shallow-clones the upstream ref,
copies the package tree under the repo's OWN `_vendor/<lib>/` tree,
preserves/copies `LICENSE`, and stamps the entry's `vendored_at`.

The destination is RESOLVED from the git index rather than hardcoded
(work-item `livespec-dev-tooling-w25v`): the fleet uses three distinct
vendor layouts — `.claude-plugin/scripts/_vendor/` (livespec,
beads-fabro, git-jsonl), `<package>/_vendor/` (livespec-dev-tooling
itself), and `_vendor/` at the repo root (livespec-driver-claude) — so
a hardcoded plugin-layout path silently wrote a fresh wrong-place tree
in two of the five repos that carry one, including the repo that SHIPS
this tool.

It was RELOCATED from livespec-core's `dev-tooling/vendor_update.py`
into this installed package (work-item livespec-9ixg) so the fleet's
release→bump-pin automation can re-vendor in every consumer repo. The
first test below asserts the NEW import path resolves — the load-bearing
proof of the relocation.

The clone step is driven by a fake `git` shim on PATH (the precedent
from `test_tdd_commit.py`): the shim materializes a clone tree in the
`git clone ... <dest>` destination so the copy + license + manifest-stamp
legs run without network access. GIT_* hook-passthrough vars are scrubbed
so the subprocess does not inherit a surrounding hook's repo context.
"""

from __future__ import annotations

import importlib.util
import os
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULE = _REPO_ROOT / "livespec_dev_tooling" / "vendor_update.py"

_GIT_ENV_PASSTHROUGH_VARS: tuple[str, ...] = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_COMMON_DIR",
    "GIT_NAMESPACE",
    "GIT_LITERAL_PATHSPECS",
    "GIT_PREFIX",
)

_EXIT_PRECONDITION = 3

_LIB = "examplelib"
_UPSTREAM_URL = "https://github.com/example/examplelib"
_UPSTREAM_REF = "1.2.3"
_OLD_VENDORED_AT = "2026-01-01T00:00:00Z"


def _scrubbed_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in _GIT_ENV_PASSTHROUGH_VARS}


def _manifest_text(
    *,
    name: str = _LIB,
    upstream_url: str = _UPSTREAM_URL,
    upstream_ref: str = _UPSTREAM_REF,
    vendored_at: str = _OLD_VENDORED_AT,
    shim: bool = False,
) -> str:
    """Build a `.vendor.jsonc` whose single entry matches the rewrite needle.

    The key order (`name` → `upstream_url` → `upstream_ref` →
    `vendored_at`) and the six-space indentation reproduce the literal
    text the module's targeted in-place `vendored_at` rewrite searches
    for, so the happy-path stamp succeeds.
    """
    shim_line = ',\n      "shim": true' if shim else ""
    return (
        "// .vendor.jsonc — test manifest.\n"
        "{\n"
        '  "libraries": [\n'
        "    {\n"
        f'      "name": "{name}",\n'
        f'      "upstream_url": "{upstream_url}",\n'
        f'      "upstream_ref": "{upstream_ref}",\n'
        f'      "vendored_at": "{vendored_at}"{shim_line}\n'
        "    }\n"
        "  ]\n"
        "}\n"
    )


_PLUGIN_VENDOR_ROOT = ".claude-plugin/scripts/_vendor"
_PACKAGE_VENDOR_ROOT = "livespec_dev_tooling/_vendor"
_ROOT_VENDOR_ROOT = "_vendor"

# The default tracked listing: one pre-existing vendored lib under the plugin
# layout, which is what the majority of the fleet carries. Tests that exercise
# a DIFFERENT layout, an ambiguous repo, or an unvendored one pass their own.
_DEFAULT_TRACKED: tuple[str, ...] = (f"{_PLUGIN_VENDOR_ROOT}/otherlib/__init__.py",)


def _write_fake_git(
    *,
    bin_dir: Path,
    make_package_dir: bool = True,
    upstream_license: bool = True,
    tracked: tuple[str, ...] = _DEFAULT_TRACKED,
) -> None:
    """Write an executable fake `git` shim that materializes a clone tree.

    On `git clone ... <dest>` the shim creates `<dest>` and, when
    `make_package_dir`, a `<dest>/<lib>/` package tree (a top-level
    module file, a sub-package dir, and a `__pycache__` dir the copy
    must skip). When `upstream_license`, it also writes `<dest>/LICENSE`.

    On `git ls-files` it prints `tracked` verbatim — the repo's INDEX,
    which is what destination resolution reads. Passing the listing
    explicitly (rather than walking the tmp tree) is what lets a test
    put a `_vendor/` directory on disk that the index does NOT carry,
    the false positive a filesystem walk would take.

    Any other git subcommand exits 0.
    """
    tracked_block = (
        "if [ \"$1\" = 'ls-files' ]; then\n"
        + "".join(f'  echo "{entry}"\n' for entry in tracked)
        + "  exit 0\n"
        "fi\n"
    )
    package_block = (
        f'  mkdir -p "$DEST/{_LIB}/subpkg"\n'
        f'  mkdir -p "$DEST/{_LIB}/__pycache__"\n'
        f'  echo "x = 1" > "$DEST/{_LIB}/__init__.py"\n'
        f'  echo "y = 2" > "$DEST/{_LIB}/subpkg/mod.py"\n'
        f'  echo "cached" > "$DEST/{_LIB}/__pycache__/stale.pyc"\n'
        if make_package_dir
        else "  :\n"
    )
    license_block = (
        '  echo "UPSTREAM LICENSE TEXT" > "$DEST/LICENSE"\n' if upstream_license else "  :\n"
    )
    bin_dir.mkdir(parents=True, exist_ok=True)
    git_path = bin_dir / "git"
    git_path.write_text(
        "#!/usr/bin/env bash\n"
        'if [ "$1" = "clone" ]; then\n'
        '  DEST="${@: -1}"\n'
        '  mkdir -p "$DEST"\n'
        f"{package_block}"
        f"{license_block}"
        "  exit 0\n"
        "fi\n"
        f"{tracked_block}"
        "exit 0\n",
        encoding="utf-8",
    )
    git_path.chmod(git_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _run_module(
    *,
    cwd: Path,
    bin_dir: Path,
    lib: str = _LIB,
) -> subprocess.CompletedProcess[str]:
    """Invoke vendor_update as a subprocess with the fake git shim first on PATH."""
    env = _scrubbed_env()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
    return subprocess.run(
        [sys.executable, str(_MODULE), lib],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _vendor_dest(*, root: Path, lib: str = _LIB, vendor_root: str = _PLUGIN_VENDOR_ROOT) -> Path:
    return root / vendor_root / lib


# ---------------------------------------------------------------------------
# Relocation proof — the NEW import path resolves and is invocable.
# ---------------------------------------------------------------------------


def test_module_resolves_at_new_package_path() -> None:
    """`livespec_dev_tooling.vendor_update` imports and exposes `main` (relocation)."""
    spec = importlib.util.spec_from_file_location("vendor_update_relocation", str(_MODULE))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main)


# ---------------------------------------------------------------------------
# Happy path — clone, copy package tree (skipping __pycache__), upstream
# LICENSE, stamp vendored_at.
# ---------------------------------------------------------------------------


def test_happy_path_vendors_and_stamps(*, tmp_path: Path) -> None:
    """Exit 0: package tree copied (no __pycache__), LICENSE copied, manifest stamped."""
    (tmp_path / ".vendor.jsonc").write_text(_manifest_text(), encoding="utf-8")
    bin_dir = tmp_path / "fakebin"
    _write_fake_git(bin_dir=bin_dir)

    result = _run_module(cwd=tmp_path, bin_dir=bin_dir)
    assert result.returncode == 0, f"expected exit 0; stderr={result.stderr!r}"

    dest = _vendor_dest(root=tmp_path)
    assert (dest / "__init__.py").read_text(encoding="utf-8") == "x = 1\n"
    assert (dest / "subpkg" / "mod.py").read_text(encoding="utf-8") == "y = 2\n"
    assert not (dest / "__pycache__").exists(), "__pycache__ must be skipped on copy"
    assert (dest / "LICENSE").read_text(encoding="utf-8") == "UPSTREAM LICENSE TEXT\n"

    manifest = (tmp_path / ".vendor.jsonc").read_text(encoding="utf-8")
    assert _OLD_VENDORED_AT not in manifest, "vendored_at must be rewritten"
    assert "vendor-update completed" in result.stderr


def test_happy_path_overwrites_existing_vendor_dest(*, tmp_path: Path) -> None:
    """A pre-existing vendor_dest dir is rmtree'd and replaced (no stale files)."""
    (tmp_path / ".vendor.jsonc").write_text(_manifest_text(), encoding="utf-8")
    dest = _vendor_dest(root=tmp_path)
    dest.mkdir(parents=True)
    (dest / "stale.txt").write_text("old\n", encoding="utf-8")
    bin_dir = tmp_path / "fakebin"
    _write_fake_git(bin_dir=bin_dir)

    result = _run_module(cwd=tmp_path, bin_dir=bin_dir)
    assert result.returncode == 0, f"stderr={result.stderr!r}"
    assert not (dest / "stale.txt").exists(), "stale pre-existing file must be gone"
    assert (dest / "__init__.py").exists()


# ---------------------------------------------------------------------------
# Destination resolution (`livespec-dev-tooling-w25v`) — the layout is READ
# from the git index, never assumed. Three layouts exist in the fleet and a
# hardcoded one is wrong in two of the five repos that carry a vendor tree.
# ---------------------------------------------------------------------------


def test_resolves_package_layout_vendor_root(*, tmp_path: Path) -> None:
    """`<package>/_vendor/` — the layout of the repo that SHIPS this tool.

    livespec-dev-tooling is a plain library with no `.claude-plugin/` tree;
    its vendored libs live at `livespec_dev_tooling/_vendor/`. Under the
    hardcoded destination the blessed path could not re-vendor in its own
    home, which is how `w25v` was found.
    """
    (tmp_path / ".vendor.jsonc").write_text(_manifest_text(), encoding="utf-8")
    bin_dir = tmp_path / "fakebin"
    _write_fake_git(bin_dir=bin_dir, tracked=(f"{_PACKAGE_VENDOR_ROOT}/tomli/__init__.py",))

    result = _run_module(cwd=tmp_path, bin_dir=bin_dir)
    assert result.returncode == 0, f"stderr={result.stderr!r}"

    dest = _vendor_dest(root=tmp_path, vendor_root=_PACKAGE_VENDOR_ROOT)
    assert (dest / "__init__.py").read_text(encoding="utf-8") == "x = 1\n"
    assert not _vendor_dest(
        root=tmp_path
    ).exists(), "the plugin-layout path must not be created in a package-layout repo"


def test_resolves_repo_root_vendor_layout(*, tmp_path: Path) -> None:
    """`_vendor/` at the repo ROOT — livespec-driver-claude's layout.

    The named counterexample that proves one re-vendor invocation does not
    fit the fleet: three repos vendor under `.claude-plugin/scripts/`, this
    one does not.
    """
    (tmp_path / ".vendor.jsonc").write_text(_manifest_text(), encoding="utf-8")
    bin_dir = tmp_path / "fakebin"
    _write_fake_git(bin_dir=bin_dir, tracked=(f"{_ROOT_VENDOR_ROOT}/returns/__init__.py",))

    result = _run_module(cwd=tmp_path, bin_dir=bin_dir)
    assert result.returncode == 0, f"stderr={result.stderr!r}"

    dest = _vendor_dest(root=tmp_path, vendor_root=_ROOT_VENDOR_ROOT)
    assert (dest / "__init__.py").read_text(encoding="utf-8") == "x = 1\n"
    assert not _vendor_dest(root=tmp_path).exists()


def test_no_tracked_vendor_tree_exits_3(*, tmp_path: Path) -> None:
    """A repo with NO vendored tree → exit 3, not a fresh wrong-place tree.

    This is the fail-loud arm, and it is the one that matters most: the old
    behaviour created `.claude-plugin/scripts/_vendor/<lib>/` and exited 0,
    so a repo that had never vendored anything acquired a tree in a location
    nothing imports from. Establishing a FIRST tree is the one-time manual
    procedure (livespec `SPECIFICATION/constraints.md` section "Vendoring
    procedure"); this tool re-vendors an existing one.
    """
    (tmp_path / ".vendor.jsonc").write_text(_manifest_text(), encoding="utf-8")
    bin_dir = tmp_path / "fakebin"
    _write_fake_git(bin_dir=bin_dir, tracked=("livespec_runtime/hygiene_scan.py",))

    result = _run_module(cwd=tmp_path, bin_dir=bin_dir)
    assert result.returncode == _EXIT_PRECONDITION, f"stderr={result.stderr!r}"
    assert "no tracked `_vendor/` tree" in result.stderr
    assert not _vendor_dest(root=tmp_path).exists(), "must not create a wrong-place tree"


def test_ambiguous_vendor_trees_exit_3(*, tmp_path: Path) -> None:
    """Two tracked `_vendor/` trees → exit 3 naming both, rather than picking one."""
    (tmp_path / ".vendor.jsonc").write_text(_manifest_text(), encoding="utf-8")
    bin_dir = tmp_path / "fakebin"
    _write_fake_git(
        bin_dir=bin_dir,
        tracked=(
            f"{_PLUGIN_VENDOR_ROOT}/otherlib/__init__.py",
            f"{_PACKAGE_VENDOR_ROOT}/tomli/__init__.py",
        ),
    )

    result = _run_module(cwd=tmp_path, bin_dir=bin_dir)
    assert result.returncode == _EXIT_PRECONDITION, f"stderr={result.stderr!r}"
    assert "more than one tracked `_vendor/` tree" in result.stderr
    assert _PLUGIN_VENDOR_ROOT in result.stderr and _PACKAGE_VENDOR_ROOT in result.stderr


def test_untracked_vendor_tree_on_disk_is_ignored(*, tmp_path: Path) -> None:
    """An on-disk `_vendor/` the index does not carry is NOT a destination.

    Every governed repo's virtualenv contains
    `.venv/lib/python3.10/site-packages/livespec_dev_tooling/_vendor/` — the
    INSTALLED dependency — so a filesystem walk answers YES in repos that
    vendor nothing. That false positive is recorded in this thread as having
    briefly produced a wrong conclusion about which repos vendor. Resolution
    reads `git ls-files`, so the untracked copy is invisible and the repo is
    correctly reported as unvendored.
    """
    (tmp_path / ".vendor.jsonc").write_text(_manifest_text(), encoding="utf-8")
    installed = tmp_path / ".venv/lib/python3.10/site-packages/livespec_dev_tooling/_vendor/returns"
    installed.mkdir(parents=True)
    (installed / "__init__.py").write_text("vendored-by-the-dependency\n", encoding="utf-8")
    bin_dir = tmp_path / "fakebin"
    _write_fake_git(bin_dir=bin_dir, tracked=("livespec_runtime/hygiene_scan.py",))

    result = _run_module(cwd=tmp_path, bin_dir=bin_dir)
    assert result.returncode == _EXIT_PRECONDITION, f"stderr={result.stderr!r}"
    assert "no tracked `_vendor/` tree" in result.stderr
    assert (installed / "__init__.py").read_text(encoding="utf-8") == (
        "vendored-by-the-dependency\n"
    ), "the installed dependency's vendor tree must never be written to"


# ---------------------------------------------------------------------------
# LICENSE branches.
# ---------------------------------------------------------------------------


def test_no_upstream_license_restores_preexisting(*, tmp_path: Path) -> None:
    """Upstream ships no LICENSE but vendor_dest had one → it is restored (warning)."""
    (tmp_path / ".vendor.jsonc").write_text(_manifest_text(), encoding="utf-8")
    dest = _vendor_dest(root=tmp_path)
    dest.mkdir(parents=True)
    (dest / "LICENSE").write_text("MAINTAINER-AUTHORED LICENSE\n", encoding="utf-8")
    bin_dir = tmp_path / "fakebin"
    _write_fake_git(bin_dir=bin_dir, upstream_license=False)

    result = _run_module(cwd=tmp_path, bin_dir=bin_dir)
    assert result.returncode == 0, f"stderr={result.stderr!r}"
    assert (dest / "LICENSE").read_text(encoding="utf-8") == "MAINTAINER-AUTHORED LICENSE\n"
    assert "restored pre-existing" in result.stderr


def test_no_upstream_license_and_no_preexisting_warns(*, tmp_path: Path) -> None:
    """No upstream LICENSE and no pre-existing one → warning, still exits 0."""
    (tmp_path / ".vendor.jsonc").write_text(_manifest_text(), encoding="utf-8")
    bin_dir = tmp_path / "fakebin"
    _write_fake_git(bin_dir=bin_dir, upstream_license=False)

    result = _run_module(cwd=tmp_path, bin_dir=bin_dir)
    assert result.returncode == 0, f"stderr={result.stderr!r}"
    assert "maintainer must author one" in result.stderr
    assert not (_vendor_dest(root=tmp_path) / "LICENSE").exists()


# ---------------------------------------------------------------------------
# Precondition failures (exit 3).
# ---------------------------------------------------------------------------


def test_missing_manifest_exits_3(*, tmp_path: Path) -> None:
    """No `.vendor.jsonc` in cwd → exit 3, manifest-not-found logged."""
    bin_dir = tmp_path / "fakebin"
    _write_fake_git(bin_dir=bin_dir)
    result = _run_module(cwd=tmp_path, bin_dir=bin_dir)
    assert result.returncode == _EXIT_PRECONDITION
    assert "manifest not found" in result.stderr


def test_manifest_without_libraries_array_exits_3(*, tmp_path: Path) -> None:
    """A manifest whose `libraries` is not a list → exit 3."""
    (tmp_path / ".vendor.jsonc").write_text('{ "libraries": "nope" }\n', encoding="utf-8")
    bin_dir = tmp_path / "fakebin"
    _write_fake_git(bin_dir=bin_dir)
    result = _run_module(cwd=tmp_path, bin_dir=bin_dir)
    assert result.returncode == _EXIT_PRECONDITION
    assert "missing top-level `libraries` array" in result.stderr


def test_no_entry_for_lib_exits_3(*, tmp_path: Path) -> None:
    """The requested lib has no `.vendor.jsonc` entry → exit 3."""
    (tmp_path / ".vendor.jsonc").write_text(_manifest_text(name="other"), encoding="utf-8")
    bin_dir = tmp_path / "fakebin"
    _write_fake_git(bin_dir=bin_dir)
    result = _run_module(cwd=tmp_path, lib=_LIB, bin_dir=bin_dir)
    assert result.returncode == _EXIT_PRECONDITION
    assert "no `.vendor.jsonc` entry for lib" in result.stderr


def test_shim_entry_is_not_revendored_exits_3(*, tmp_path: Path) -> None:
    """A `shim: true` entry is refused → exit 3 (shims edited in place, not vendored)."""
    (tmp_path / ".vendor.jsonc").write_text(_manifest_text(shim=True), encoding="utf-8")
    bin_dir = tmp_path / "fakebin"
    _write_fake_git(bin_dir=bin_dir)
    result = _run_module(cwd=tmp_path, bin_dir=bin_dir)
    assert result.returncode == _EXIT_PRECONDITION
    assert "lib is a shim" in result.stderr


def test_clone_missing_package_dir_exits_3(*, tmp_path: Path) -> None:
    """Clone produces no `<lib>/` package dir → _copy_package_tree raises exit 3."""
    (tmp_path / ".vendor.jsonc").write_text(_manifest_text(), encoding="utf-8")
    bin_dir = tmp_path / "fakebin"
    _write_fake_git(bin_dir=bin_dir, make_package_dir=False)
    result = _run_module(cwd=tmp_path, bin_dir=bin_dir)
    assert result.returncode == _EXIT_PRECONDITION


def test_manifest_needle_format_mismatch_exits_3(*, tmp_path: Path) -> None:
    """Entry parses but its on-disk text differs from the rewrite needle → exit 3.

    The clone + copy legs succeed (the entry is valid), but the
    single-line manifest formatting does not contain the literal
    multi-line `vendored_at` needle, so the targeted in-place rewrite
    refuses rather than corrupt the manifest.
    """
    (tmp_path / ".vendor.jsonc").write_text(
        '{ "libraries": [ '
        f'{{ "name": "{_LIB}", "upstream_url": "{_UPSTREAM_URL}", '
        f'"upstream_ref": "{_UPSTREAM_REF}", "vendored_at": "{_OLD_VENDORED_AT}" }} '
        "] }\n",
        encoding="utf-8",
    )
    bin_dir = tmp_path / "fakebin"
    _write_fake_git(bin_dir=bin_dir)
    result = _run_module(cwd=tmp_path, bin_dir=bin_dir)
    assert result.returncode == _EXIT_PRECONDITION


# ---------------------------------------------------------------------------
# Defensive branch reached by importing the module directly: the
# `_rewrite_vendored_at` entry-None guard is unreachable via the public
# flow (the caller already located the entry), so it is exercised by
# calling the private helper against a manifest that lacks the lib.
# ---------------------------------------------------------------------------


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("vendor_update_unit", str(_MODULE))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rewrite_vendored_at_missing_entry_raises(*, tmp_path: Path) -> None:
    """`_rewrite_vendored_at` raises SystemExit(3) when the entry is absent."""
    module = _load_module()
    manifest = tmp_path / ".vendor.jsonc"
    manifest.write_text(_manifest_text(name="other"), encoding="utf-8")
    with pytest.raises(SystemExit) as excinfo:
        _ = module._rewrite_vendored_at(  # noqa: SLF001  — private helper under test
            manifest_path=manifest, lib_name=_LIB, now_iso="2026-06-21T00:00:00Z"
        )
    assert excinfo.value.code == _EXIT_PRECONDITION


def test_module_re_import_with_vendor_in_sys_path() -> None:
    """Re-importing when _VENDOR_DIR is already on sys.path covers the False branch."""
    first = _load_module()
    assert callable(first.main)
    second = _load_module()
    assert callable(second.main)


def _imports_vendored_returns(*, source: str) -> bool:
    """True iff `source` has a module-level import of the VENDORED `returns`."""
    return any(line.startswith(("from returns", "import returns")) for line in source.splitlines())


def test_every_returns_importing_module_carries_the_vendor_path_preamble() -> None:
    """A first-party module importing `returns` must put `_vendor/` on the path ITSELF.

    `returns` is VENDORED, not installed, so a bare `from returns... import`
    resolves only if some EARLIER import in the same process already inserted
    `_vendor/` into `sys.path`. That makes a bare import work everywhere the
    module is reached BY IMPORT and fail wherever it is the process ENTRY
    POINT — the one environment no unit test exercises, because a test suite
    has always imported something else first.

    THAT IS NOT HYPOTHETICAL, AND THIS TEST EXISTS BECAUSE IT SHIPPED.
    `cross_repo/ci_yaml_canonical_reconcile.py` gained a bare
    `from returns.unsafe import unsafe_perform_io` in `89296e0`, the
    `livespec-dev-tooling-vzwa` conversion. Its whole in-repo test suite
    passed. It is also invoked as `python -m
    livespec_dev_tooling.cross_repo.ci_yaml_canonical_reconcile` by the
    reusable bump-pin workflow, where it is the entry point and nothing ran
    before it — so every consumer's pin bump died on `ModuleNotFoundError: No
    module named 'returns'`, and SEVEN of eight fleet members sat stuck at
    `v1.8.4` while this repo released `v1.12.0`.

    It asserts the invariant over the WHOLE first-party tree rather than over
    the one module that broke, because the failing environment is invisible to
    every other test in this suite: the next module to grow a `returns` import
    has no local signal that it needs the preamble.

    It is the mechanical form of this fleet's THIRD AXIS
    (`livespec-dev-tooling-zu85` / `-dx8l`): "CAN this module import `returns`
    at all, in EVERY environment it executes in?" — independent of whether the
    conversion itself was correct, and not answered by answering the railway
    question well.
    """
    package_root = Path(__file__).resolve().parents[2] / "livespec_dev_tooling"
    sources = {
        path: path.read_text(encoding="utf-8")
        for path in sorted(package_root.rglob("*.py"))
        if "_vendor" not in path.parts and "__pycache__" not in path.parts
    }
    importers = {
        path: text for path, text in sources.items() if _imports_vendored_returns(source=text)
    }
    offenders = sorted(
        path.relative_to(package_root).as_posix()
        for path, text in importers.items()
        if "_VENDOR_DIR" not in text
    )
    # THE DENOMINATOR, asserted rather than assumed. `offenders == []` over an
    # EMPTY importer set is byte-identical green to `offenders == []` over a
    # correct one, and telling those two apart is this repo's entire subject.
    assert importers, f"swept {len(sources)} modules and found NONE importing `returns`"
    assert offenders == [], (
        "these modules import the VENDORED `returns` without putting `_vendor/` on "
        f"sys.path themselves, so they break when run as `python -m`: {offenders}"
    )

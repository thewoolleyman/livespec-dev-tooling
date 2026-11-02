"""The provisioner's volume `setup` script, run a SECOND time on a volume it seeded, leaves the seed alone.

livespec-dev-tooling-5j5x. Measured 2026-11-02 on poweredge-xubuntu: the
local-path provisioner provisioned claim pvc-ece227b1 twice (``Creating
volume`` at 21:42:23Z, ProvisioningSucceeded at 21:42:55Z, ``Creating volume``
again at 21:42:55Z). The runner pod was already running on the first seed, and
the second setup run began by DROPPING the externals seed. The ARC hook, reading
at 21:43:21Z, found no marker, fell back to upstream's copy, and failed
``EACCES: permission denied, mkdir '/home/runner/_work/externals/node20'`` in
the half re-created tree.

These tests EXECUTE the committed script under ``/bin/sh`` against a scratch
node path. A ``cp`` shim on PATH drops ``--reflink=always``, so the scratch
filesystem need not support reflinks: the property under test is what a re-run
does to a seeded volume, not how the bytes are cloned.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

__all__: list[str] = []

_REPO = Path(__file__).resolve().parents[2]
_PROVISIONER = (
    _REPO
    / "ci-runner"
    / "k3s"
    / "phase2"
    / "local-path-provisioner"
    / "local-path-provisioner.yaml"
)
_SETUP_SCRIPT = re.compile(r"^  setup: \|-\n(?P<body>.*?)\n  [a-z]", re.MULTILINE | re.DOTALL)
_VERSION = "2.336.0"


def _setup_script() -> str:
    match = _SETUP_SCRIPT.search(_PROVISIONER.read_text(encoding="utf-8"))
    assert match is not None, f"no `setup: |-` block in {_PROVISIONER}"
    return "\n".join(line[4:] for line in match.group("body").splitlines()) + "\n"


def _node_path(*, root: Path) -> Path:
    """A scratch node path holding a published externals copy and a warm uv generation."""
    node = root / "storage"
    version_dir = node / ".externals" / _VERSION
    for runtime in ("node20", "node20_alpine", "node24", "node24_alpine"):
        (version_dir / runtime / "bin").mkdir(parents=True)
        (version_dir / runtime / "bin" / "node").write_text(runtime, encoding="utf-8")
    (version_dir / f".externals-seeded-{_VERSION}").write_text(f"{_VERSION}\n", encoding="utf-8")
    (node / ".externals" / "current").symlink_to(_VERSION)
    generation = node / ".warm" / "20261102T000000Z"
    (generation / "archive-v0").mkdir(parents=True)
    (generation / "archive-v0" / "entry").write_text("wheel", encoding="utf-8")
    (node / ".warm" / "uv").symlink_to("20261102T000000Z")
    return node


def _cp_shim(*, root: Path) -> Path:
    shim_dir = root / "shim"
    shim_dir.mkdir()
    shim = shim_dir / "cp"
    shim.write_text(
        '#!/bin/sh\nfor a in "$@"; do shift; [ "$a" = --reflink=always ] || set -- "$@" "$a"; done\n'
        'exec /bin/cp "$@"\n',
        encoding="utf-8",
    )
    shim.chmod(0o755)
    return shim_dir


def _run_setup(*, root: Path, vol_dir: Path, script: Path, shim_dir: Path) -> None:
    env = {
        **os.environ,
        "PATH": f"{shim_dir}:{os.environ['PATH']}",
        "VOL_DIR": str(vol_dir),
        "VOL_MODE": "Filesystem",
        "VOL_SIZE_BYTES": "0",
    }
    completed = subprocess.run(
        ["/bin/sh", str(script)], env=env, cwd=root, capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stderr


def _seeded_volume(*, tmp_path: Path) -> tuple[Path, Path, Path]:
    node = _node_path(root=tmp_path)
    script = tmp_path / "setup"
    script.write_text(_setup_script(), encoding="utf-8")
    shim_dir = _cp_shim(root=tmp_path)
    vol_dir = node / "pvc-0000_arc-runners_runner-x-work"
    _run_setup(root=tmp_path, vol_dir=vol_dir, script=script, shim_dir=shim_dir)
    return vol_dir, script, shim_dir


def test_a_first_setup_seeds_externals_with_its_marker_and_the_warm_cache(tmp_path: Path) -> None:
    vol_dir, _, _ = _seeded_volume(tmp_path=tmp_path)
    assert (vol_dir / "externals" / "node20" / "bin" / "node").is_file()
    assert (vol_dir / "externals" / f".externals-seeded-{_VERSION}").read_text(
        encoding="utf-8"
    ).strip() == _VERSION
    assert (vol_dir / "_warm" / "uv" / "archive-v0" / "entry").is_file()


def test_a_second_setup_on_a_seeded_volume_leaves_its_seed_untouched(tmp_path: Path) -> None:
    vol_dir, script, shim_dir = _seeded_volume(tmp_path=tmp_path)
    externals_inode = (vol_dir / "externals").stat().st_ino
    marker = vol_dir / "externals" / f".externals-seeded-{_VERSION}"
    marker_inode = marker.stat().st_ino
    warm_inode = (vol_dir / "_warm").stat().st_ino
    # A running job's own write into its warm cache must survive the re-run too.
    job_write = vol_dir / "_warm" / "uv" / "job-written"
    job_write.write_text("job", encoding="utf-8")

    _run_setup(root=tmp_path, vol_dir=vol_dir, script=script, shim_dir=shim_dir)

    assert (
        (vol_dir / "externals").stat().st_ino == externals_inode
    ), "the re-run replaced the externals tree a running job's hook may be reading"
    assert marker.stat().st_ino == marker_inode, "the re-run removed and re-wrote the marker"
    assert (vol_dir / "_warm").stat().st_ino == warm_inode, "the re-run replaced the warm seed"
    assert job_write.is_file(), "the re-run deleted a running job's warm-cache write"


def test_the_externals_seed_is_renamed_into_place_rather_than_copied_there() -> None:
    script = _setup_script()
    runnable = "\n".join(line for line in script.splitlines() if not line.lstrip().startswith("#"))
    assert re.search(r'\bcp [^\n]*"\$\{VOL_DIR\}/externals"(\s|;|$)', runnable) is None, (
        "the externals seed must be copied to a staging name and renamed into place, so a "
        "starting job never sees a partial tree at <volume>/externals"
    )
    assert re.search(
        r'mv [^\n]*"\$\{VOL_DIR\}/externals"', runnable
    ), "no rename of a completed externals staging copy into <volume>/externals"

"""The factory workspace sweep archives before it removes and keeps anything it cannot prove safe.

Incident `livespec-dev-tooling-3q3xma`. These tests load the committed role script and run its
keep rules and its whole pass against a temporary workspace root, with the git, pod-list and
free-space reads replaced, so nothing here touches a host.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import time
from pathlib import Path
from types import ModuleType

import pytest

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = (
    _REPO_ROOT
    / "ansible"
    / "roles"
    / "factory_workspace_sweep"
    / "files"
    / "factory_workspace_sweep.py"
)
_HEAD = "a" * 40
_OLD = time.time() - 3 * 86400


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("factory_workspace_sweep_under_test", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def _row(name: str, *, action: str = "archive", kb: int = 1024) -> dict:
    return {
        "dir": name,
        "kb": kb,
        "cls": "item-ready",
        "head": _HEAD,
        "dirty": False,
        "evidence": "head-on-no-fetched-origin-ref",
        "item": "x-1",
        "repo": "r",
        "action": action,
    }


def _make(root: Path, name: str, *, age: float = _OLD) -> Path:
    directory = root / name
    directory.mkdir()
    (directory / "file.txt").write_text("work")
    os.utime(directory, (age, age))
    return directory


def test_a_directory_that_is_a_plain_old_unreferenced_unmoved_checkout_has_no_keep_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sweep = _load()
    _make(tmp_path, "petri-a-l0")
    monkeypatch.setattr(sweep, "head_of", lambda _directory: _HEAD)
    assert (
        sweep.keep_reason(row=_row("petri-a-l0"), root=tmp_path, refs=set(), min_age_s=86400)
        is None
    )


@pytest.mark.parametrize("why", ["pod", "young", "moved", "unreadable", "missing"])
def test_a_directory_with_any_doubt_is_kept(
    *, why: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sweep = _load()
    _make(tmp_path, "petri-a-l0", age=time.time() if why == "young" else _OLD)
    monkeypatch.setattr(sweep, "head_of", lambda _directory: "b" * 40 if why == "moved" else _HEAD)
    refs: set[str] | None = {str(tmp_path / "petri-a-l0")} if why == "pod" else set()
    if why == "unreadable":
        refs = None
    name = "petri-gone-l0" if why == "missing" else "petri-a-l0"
    reason = sweep.keep_reason(row=_row(name), root=tmp_path, refs=refs, min_age_s=86400)
    assert reason is not None


def test_report_only_is_the_default_and_removes_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sweep = _load()
    root, archive = tmp_path / "root", tmp_path / "archive"
    root.mkdir()
    _make(root, "petri-a-l0")
    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps([_row("petri-a-l0")]))
    monkeypatch.setattr(sweep, "head_of", lambda _directory: _HEAD)
    monkeypatch.setattr(sweep, "referenced_dirs", lambda _kubectl, _scope: set())
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "x",
            "--manifest",
            str(manifest),
            "--root",
            str(root),
            "--archive-dir",
            str(archive),
            "--stop-free-gib",
            "100000",
        ],
    )
    assert sweep.main() == 0
    assert (root / "petri-a-l0").is_dir()
    assert not archive.exists()
    assert "REPORT ARCHIVE petri-a-l0" in capsys.readouterr().out


@pytest.mark.skipif(
    shutil.which("zstd") is None or shutil.which("tar") is None, reason="needs zstd and tar"
)
def test_apply_archives_with_a_verified_digest_before_it_removes_the_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sweep = _load()
    root, archive = tmp_path / "root", tmp_path / "archive"
    root.mkdir()
    _make(root, "petri-a-l0")
    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps([_row("petri-a-l0")]))
    monkeypatch.setattr(sweep, "head_of", lambda _directory: _HEAD)
    monkeypatch.setattr(sweep, "referenced_dirs", lambda _kubectl, _scope: set())
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "x",
            "--manifest",
            str(manifest),
            "--root",
            str(root),
            "--archive-dir",
            str(archive),
            "--stop-free-gib",
            "100000",
            "--apply",
        ],
    )
    assert sweep.main() == 0
    assert not (root / "petri-a-l0").exists()
    record = json.loads((archive / "results.jsonl").read_text().splitlines()[0])
    assert record["sha256"] == sweep.sha256_file(archive / "petri-a-l0.tar.zst")


def test_apply_stops_once_the_free_space_target_is_met(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sweep = _load()
    root, archive = tmp_path / "root", tmp_path / "archive"
    root.mkdir()
    _make(root, "petri-a-l0")
    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps([_row("petri-a-l0", action="delete")]))
    monkeypatch.setattr(sweep, "head_of", lambda _directory: _HEAD)
    monkeypatch.setattr(sweep, "referenced_dirs", lambda _kubectl, _scope: set())
    monkeypatch.setattr(sweep, "free_bytes", lambda _root: 10**15)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "x",
            "--manifest",
            str(manifest),
            "--root",
            str(root),
            "--archive-dir",
            str(archive),
            "--stop-free-gib",
            "1",
            "--apply",
        ],
    )
    assert sweep.main() == 0
    assert (root / "petri-a-l0").is_dir()


class _Done:
    def __init__(self, *, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class _Pipe:
    def close(self) -> None:
        return None


class _Tar:
    def __init__(self, *, returncode: int = 0) -> None:
        self.stdout = _Pipe()
        self._returncode = returncode

    def wait(self) -> int:
        return self._returncode


def test_run_returns_the_completed_process_without_raising() -> None:
    sweep = _load()
    done = sweep.run(["echo", "hi"])
    assert (done.returncode, done.stdout.strip()) == (0, "hi")
    assert sweep.run(["false"]).returncode != 0


def test_free_bytes_reads_the_filesystem_under_the_root(tmp_path: Path) -> None:
    assert _load().free_bytes(tmp_path) > 0


def test_the_pod_list_names_every_hostpath_and_a_failed_read_names_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sweep = _load()
    pods = {
        "items": [
            {"spec": {"volumes": [{"hostPath": {"path": "/a/b"}}, {"emptyDir": {}}]}},
            {"spec": {}},
        ]
    }
    monkeypatch.setattr(sweep, "run", lambda _argv, **_kw: _Done(stdout=json.dumps(pods)))
    assert sweep.referenced_dirs(["k"], ["-A"]) == {"/a/b"}
    monkeypatch.setattr(sweep, "run", lambda _argv, **_kw: _Done(returncode=1))
    assert sweep.referenced_dirs(["k"], ["-A"]) is None


def test_head_of_strips_the_git_output(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    sweep = _load()
    monkeypatch.setattr(sweep, "run", lambda _argv, **_kw: _Done(stdout=_HEAD + "\n"))
    assert sweep.head_of(tmp_path) == _HEAD


def test_sha256_file_hashes_the_bytes(tmp_path: Path) -> None:
    sweep = _load()
    target = tmp_path / "f"
    target.write_bytes(b"abc")
    assert (
        sweep.sha256_file(target)
        == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def _fake_archive_tools(
    monkeypatch: pytest.MonkeyPatch, sweep: ModuleType, *, tar_rc: int, zstd_rc: int, test_rc: int
) -> None:
    monkeypatch.setattr(sweep.subprocess, "Popen", lambda *_a, **_k: _Tar(returncode=tar_rc))

    def fake_run(argv: list[str], **_kw: object) -> _Done:
        if "-t" in argv:
            return _Done(returncode=test_rc)
        Path(argv[-1]).write_bytes(b"archive")
        return _Done(returncode=zstd_rc, stderr="boom")

    monkeypatch.setattr(sweep, "run", fake_run)


@pytest.mark.parametrize(
    ("tar_rc", "zstd_rc", "test_rc", "expect"),
    [
        (0, 0, 0, None),
        (1, 0, 0, "archive-failed rc"),
        (0, 1, 0, "archive-failed rc"),
        (0, 0, 1, "archive-failed-integrity-test"),
    ],
)
def test_an_archive_is_returned_only_after_it_is_written_and_tested(
    *,
    tar_rc: int,
    zstd_rc: int,
    test_rc: int,
    expect: str | None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sweep = _load()
    _fake_archive_tools(monkeypatch, sweep, tar_rc=tar_rc, zstd_rc=zstd_rc, test_rc=test_rc)
    result = sweep.archive(root=tmp_path, name="petri-a-l0", dest_dir=tmp_path)
    if expect is None:
        assert result[0] == tmp_path / "petri-a-l0.tar.zst"
        assert result[1] == sweep.sha256_file(result[0])
    else:
        assert isinstance(result, str)
        assert result.startswith(expect)


def test_apply_row_archives_then_removes_and_a_failed_archive_keeps_the_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sweep = _load()
    root, dest = tmp_path / "root", tmp_path / "dest"
    root.mkdir()
    dest.mkdir()
    _make(root, "petri-a-l0")
    _fake_archive_tools(monkeypatch, sweep, tar_rc=1, zstd_rc=0, test_rc=0)
    record, kept = sweep.apply_row(row=_row("petri-a-l0"), root=root, dest=dest)
    assert record is None
    assert kept is not None
    assert (root / "petri-a-l0").is_dir()
    _fake_archive_tools(monkeypatch, sweep, tar_rc=0, zstd_rc=0, test_rc=0)
    record, kept = sweep.apply_row(row=_row("petri-a-l0"), root=root, dest=dest)
    assert kept is None
    assert record is not None
    assert record["sha256"]
    assert not (root / "petri-a-l0").exists()
    assert json.loads((dest / "results.jsonl").read_text().splitlines()[0])["dir"] == "petri-a-l0"


def test_apply_row_removes_a_delete_row_without_archiving(tmp_path: Path) -> None:
    sweep = _load()
    root, dest = tmp_path / "root", tmp_path / "dest"
    root.mkdir()
    dest.mkdir()
    _make(root, "petri-a-l0")
    record, kept = sweep.apply_row(row=_row("petri-a-l0", action="delete"), root=root, dest=dest)
    assert kept is None
    assert record is not None
    assert "archive" not in record
    assert not (root / "petri-a-l0").exists()


def test_the_pass_reports_keeps_and_skips_in_both_modes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sweep = _load()
    root, dest = tmp_path / "root", tmp_path / "dest"
    root.mkdir()
    _make(root, "petri-keep-l0", age=time.time())
    _make(root, "petri-fail-l0")
    manifest = tmp_path / "m.json"
    manifest.write_text(
        json.dumps(
            [_row("petri-keep-l0", kb=3), _row("petri-fail-l0", kb=2), _row("petri-skip-l0", kb=1)]
        )
    )
    monkeypatch.setattr(sweep, "head_of", lambda _directory: _HEAD)
    monkeypatch.setattr(sweep, "referenced_dirs", lambda _kubectl, _scope: set())
    _fake_archive_tools(monkeypatch, sweep, tar_rc=1, zstd_rc=0, test_rc=0)
    base = [
        "x",
        "--manifest",
        str(manifest),
        "--root",
        str(root),
        "--archive-dir",
        str(dest),
        "--stop-free-gib",
        "100000000",
    ]
    monkeypatch.setattr(sys, "argv", [*base, "--apply"])
    assert sweep.main() == 0
    out = capsys.readouterr().out
    assert "APPLY KEEP petri-keep-l0 under-minimum-age" in out
    assert "APPLY KEEP petri-fail-l0 archive-failed" in out
    monkeypatch.setattr(sys, "argv", base)
    assert sweep.main() == 0
    assert "REPORT KEEP petri-skip-l0 not-a-plain-directory" in capsys.readouterr().out


def test_a_whole_apply_pass_records_each_archived_and_removed_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sweep = _load()
    root, dest = tmp_path / "root", tmp_path / "dest"
    root.mkdir()
    _make(root, "petri-a-l0")
    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps([_row("petri-a-l0")]))
    monkeypatch.setattr(sweep, "head_of", lambda _directory: _HEAD)
    monkeypatch.setattr(sweep, "referenced_dirs", lambda _kubectl, _scope: set())
    _fake_archive_tools(monkeypatch, sweep, tar_rc=0, zstd_rc=0, test_rc=0)
    argv = ["x", "--manifest", str(manifest), "--root", str(root), "--archive-dir", str(dest)]
    monkeypatch.setattr(sys, "argv", [*argv, "--stop-free-gib", "100000000", "--apply"])
    assert sweep.main() == 0
    assert "APPLY DONE" in capsys.readouterr().out
    assert not (root / "petri-a-l0").exists()

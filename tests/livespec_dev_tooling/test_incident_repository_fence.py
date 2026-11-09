"""Real repository-lock inheritance, reentrancy and principal transport."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import selectors
import subprocess
import sys
import time
from contextlib import ExitStack
from threading import Event, Thread

import pytest

import livespec_dev_tooling._incident_observer_store as store
import livespec_dev_tooling.incident_inverse_service as inverse_service
from livespec_dev_tooling._incident_observer_store import (
    REPOSITORY_FENCE_FD_ENV,
    borrow_repository_fence,
    current_repository_fence,
    repository_lock,
)
from livespec_dev_tooling.incident_inverse_service import ProcessInverseForge

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-dln3ac
_REPOSITORY = "controlled/repository"


def _uninstrumented_env():
    """Child env without coverage startup hooks (subprocess_spawn_allowlist contract)."""
    return {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("COVERAGE_", "COV_CORE_"))
    }


def _path(directory):
    return directory / (hashlib.sha256(_REPOSITORY.encode()).hexdigest() + ".lock")


def _assert_locked(path):
    descriptor = os.open(path, os.O_RDWR)
    try:
        with pytest.raises(BlockingIOError):
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        os.close(descriptor)


def test_verified_reentrancy_borrow_close_and_scope_lifetime(tmp_path):
    state = tmp_path / "state"
    assert current_repository_fence(repository=_REPOSITORY) is None
    with repository_lock(directory=state, repository=_REPOSITORY) as record:
        cap = current_repository_fence(repository=_REPOSITORY, directory=state)
        assert cap is not None
        with repository_lock(directory=state, repository=_REPOSITORY, existing_only=True) as inner:
            assert inner == record
        with borrow_repository_fence(
            descriptor=cap.descriptor, directory=state, repository=_REPOSITORY
        ):
            _assert_locked(_path(state))
        _assert_locked(_path(state))
        assert current_repository_fence(repository="other/repo") is None
    assert current_repository_fence(repository=_REPOSITORY) is None
    assert cap.active is False
    assert _path(state).stat().st_mode & 0o777 == 0o600


def test_old_readable_lock_converges_without_replacing_inode(tmp_path):
    path = _path(tmp_path)
    path.write_bytes(b"retained")
    path.chmod(0o644)
    before = path.stat().st_ino
    with repository_lock(directory=tmp_path, repository=_REPOSITORY):
        assert path.stat().st_ino == before
        assert path.stat().st_mode & 0o777 == 0o600
    assert path.read_bytes() == b"retained"


def _refuses(context, exception=OSError):
    with ExitStack() as stack, pytest.raises(exception, match=".+"):
        stack.enter_context(context)


def test_existing_only_refuses_missing_or_unprotected_state_without_creating(tmp_path):
    missing = tmp_path / "missing"
    _refuses(repository_lock(directory=missing, repository=_REPOSITORY, existing_only=True))
    assert not missing.exists()
    tmp_path.chmod(0o777)
    _refuses(repository_lock(directory=tmp_path, repository=_REPOSITORY, existing_only=True))
    tmp_path.chmod(0o755)
    _refuses(repository_lock(directory=tmp_path, repository=_REPOSITORY, existing_only=True))


def test_existing_only_refuses_a_group_writable_ancestor_of_a_private_leaf(tmp_path):
    outer = tmp_path / "outer"
    state = outer / "state"
    state.mkdir(parents=True, mode=0o700)
    outer.chmod(0o700)
    with repository_lock(directory=state, repository=_REPOSITORY):
        pass
    state.chmod(0o700)
    _path(state).chmod(0o600)
    with repository_lock(directory=state, repository=_REPOSITORY, existing_only=True):
        pass
    outer.chmod(0o770)
    try:
        _refuses(repository_lock(directory=state, repository=_REPOSITORY, existing_only=True))
    finally:
        outer.chmod(0o700)


@pytest.mark.parametrize("descriptor", [True, -1, 0, 1, 2, 999999])
def test_invalid_borrow_descriptor_refuses(tmp_path, descriptor):
    _refuses(
        borrow_repository_fence(descriptor=descriptor, directory=tmp_path, repository=_REPOSITORY)
    )


def test_other_open_inode_mode_and_symlink_are_not_a_held_capability(tmp_path):
    with repository_lock(directory=tmp_path, repository=_REPOSITORY):
        separate = os.open(_path(tmp_path), os.O_RDWR)
        try:
            _refuses(
                borrow_repository_fence(
                    descriptor=separate, directory=tmp_path, repository=_REPOSITORY
                ),
                BlockingIOError,
            )
        finally:
            os.close(separate)
        wrong = tmp_path / "wrong"
        wrong.write_bytes(b"")
        with wrong.open("r+b") as stream:
            _refuses(
                borrow_repository_fence(
                    descriptor=stream.fileno(), directory=tmp_path, repository=_REPOSITORY
                )
            )
        cap = current_repository_fence(repository=_REPOSITORY)
        assert cap is not None
        _path(tmp_path).chmod(0o666)
        _refuses(
            borrow_repository_fence(
                descriptor=cap.descriptor, directory=tmp_path, repository=_REPOSITORY
            )
        )
        _path(tmp_path).chmod(0o600)
        _path(tmp_path).unlink()
        _path(tmp_path).symlink_to(wrong)
        _refuses(
            borrow_repository_fence(
                descriptor=cap.descriptor, directory=tmp_path, repository=_REPOSITORY
            )
        )


def test_non_regular_lock_inode_is_refused(tmp_path):
    os.mkfifo(_path(tmp_path), 0o600)
    _refuses(repository_lock(directory=tmp_path, repository=_REPOSITORY))


def test_descriptor_reuse_and_thread_context_cannot_borrow_old_capability(tmp_path):
    with repository_lock(directory=tmp_path, repository=_REPOSITORY):
        cap = current_repository_fence(repository=_REPOSITORY)
        assert cap is not None
        results = []
        worker = Thread(
            target=lambda: results.append(current_repository_fence(repository=_REPOSITORY))
        )
        worker.start()
        worker.join(5)
        assert results == [None]
        public = cap.descriptor
        os.close(public)
        replacement = os.open(_path(tmp_path), os.O_RDWR)
        assert replacement == public
        assert current_repository_fence(repository=_REPOSITORY) is None
        _refuses(repository_lock(directory=tmp_path, repository=_REPOSITORY))
    os.close(replacement)


def test_repository_without_directory_refuses_ambiguous_live_locks(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    with (
        repository_lock(directory=first, repository=_REPOSITORY),
        repository_lock(directory=second, repository=_REPOSITORY),
    ):
        assert current_repository_fence(repository=_REPOSITORY) is None
        assert current_repository_fence(repository=_REPOSITORY, directory=first) is not None
        assert current_repository_fence(repository=_REPOSITORY, directory=second) is not None


def test_symlink_loop_is_a_named_fence_refusal(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    first.symlink_to(second)
    second.symlink_to(first)
    assert current_repository_fence(repository=_REPOSITORY, directory=first) is None
    _refuses(repository_lock(directory=first, repository=_REPOSITORY, existing_only=True))


def test_real_principal_transport_passes_only_current_verified_descriptor(tmp_path, monkeypatch):
    script = tmp_path / "principal.py"
    script.write_text(
        """import json,os,sys\nfrom pathlib import Path\nfrom livespec_dev_tooling._incident_observer_store import borrow_repository_fence\np=json.load(sys.stdin)\nk='LIVESPEC_INCIDENT_REPOSITORY_FENCE_FD'\nf=os.environ.get(k)\nif f:\n with borrow_repository_fence(descriptor=int(f),directory=Path(sys.argv[1]),repository='controlled/repository'): pass\nprint(json.dumps({'schema':1,'operation':p['operation'],'binding':p['binding'],'head':f or 'absent'}))\n"""
    )
    principal = ProcessInverseForge(command=(sys.executable, "-I", str(script), str(tmp_path)))
    monkeypatch.setenv(REPOSITORY_FENCE_FD_ENV, "untrusted-incoming-marker")
    assert principal.read_master_head(repository=_REPOSITORY, branch="master") == "absent"
    with repository_lock(directory=tmp_path, repository=_REPOSITORY):
        cap = current_repository_fence(repository=_REPOSITORY)
        assert cap is not None
        assert principal.read_master_head(repository=_REPOSITORY, branch="master") == str(
            cap.descriptor
        )


def test_child_retains_borrowed_ofd_after_owner_process_dies(tmp_path):
    child = tmp_path / "borrower.py"
    child.write_text(
        """import json,os,sys\nfrom pathlib import Path\nfrom livespec_dev_tooling._incident_observer_store import borrow_repository_fence\nwith borrow_repository_fence(descriptor=int(sys.argv[1]),directory=Path(sys.argv[2]),repository=sys.argv[3]):\n print(json.dumps({'pid':os.getpid()}),flush=True)\n sys.stdin.read(1)\n"""
    )
    owner = tmp_path / "owner.py"
    owner.write_text(
        """import os,subprocess,sys\nfrom pathlib import Path\nfrom livespec_dev_tooling._incident_observer_store import repository_lock,current_repository_fence\nwith repository_lock(directory=Path(sys.argv[1]),repository=sys.argv[3]):\n f=current_repository_fence(repository=sys.argv[3]); assert f is not None\n subprocess.Popen([sys.executable,'-I',sys.argv[2],str(f.descriptor),sys.argv[1],sys.argv[3]],pass_fds=(f.descriptor,))\n os._exit(17)\n"""
    )
    state = tmp_path / "state"
    process = subprocess.Popen(
        [sys.executable, "-I", str(owner), str(state), str(child), _REPOSITORY],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_uninstrumented_env(),
    )
    try:
        assert process.stdout is not None and process.stdin is not None
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            assert selector.select(timeout=10), "borrower did not acknowledge its actual lock"
        assert json.loads(process.stdout.readline())["pid"] > 0
        assert process.wait(timeout=10) == 17
        _assert_locked(_path(state))
        process.stdin.write(b"x")
        process.stdin.flush()
        process.stdin.close()
        assert process.stdout.read() == b""
    finally:
        assert process.stdin is not None
        process.stdin.close()
        process.kill()
        process.wait(timeout=10)


def test_malformed_transport_payload_cannot_reuse_ambient_fence(tmp_path, monkeypatch):
    script = tmp_path / "inspect.py"
    script.write_text(
        """import json,os,sys\nfrom pathlib import Path\np=json.load(sys.stdin)\nPath(sys.argv[1]).write_text(os.environ.get('LIVESPEC_INCIDENT_REPOSITORY_FENCE_FD','absent'))\nprint(json.dumps({'schema':1,'operation':p['operation'],'binding':p['binding'],'status':'unknown'}))\n"""
    )
    observed = tmp_path / "observed"
    principal = ProcessInverseForge(command=(sys.executable, "-I", str(script), str(observed)))
    with repository_lock(directory=tmp_path, repository=_REPOSITORY):
        cap = current_repository_fence(repository=_REPOSITORY)
        assert cap is not None
        monkeypatch.setenv(REPOSITORY_FENCE_FD_ENV, str(cap.descriptor))
        # A malformed serializer answer must not select an unrelated live
        # repository merely because an ambient descriptor marker exists.
        monkeypatch.setattr(inverse_service, "asdict", lambda _request: [])
        result = principal.publish_inverse(request=object())
        assert result.status == "unknown"
        assert observed.read_text() == "absent"


def test_a_bounded_acquisition_waits_for_a_release_and_gives_up_when_none_comes(tmp_path):
    holding, release = Event(), Event()

    def hold():
        with repository_lock(directory=tmp_path, repository=_REPOSITORY):
            holding.set()
            release.wait(timeout=10)

    holder = Thread(target=hold)
    holder.start()
    try:
        assert holding.wait(timeout=5)
        with pytest.raises(store.RepositoryFenceBusyError):
            ExitStack().enter_context(
                repository_lock(directory=tmp_path, repository=_REPOSITORY, wait_seconds=0.05)
            )
        Thread(target=lambda: (time.sleep(0.1), release.set())).start()
        with repository_lock(directory=tmp_path, repository=_REPOSITORY, wait_seconds=5):
            assert current_repository_fence(repository=_REPOSITORY, directory=tmp_path)
    finally:
        release.set()
        holder.join(timeout=10)


def test_a_bounded_acquisition_of_a_free_fence_succeeds_at_once(tmp_path):
    with repository_lock(directory=tmp_path, repository=_REPOSITORY, wait_seconds=0):
        assert current_repository_fence(repository=_REPOSITORY, directory=tmp_path)

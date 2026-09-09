"""Mirror-paired test for `livespec_dev_tooling/checks/_red_green_replay_revert.py`.

Pins the forge-authored-revert exemption that closes the deadlock measured
in livespec-overseer on 2026-08-22 (work-item livespec-dev-tooling-j2qa):
`livespec/.ai/ci-gate-discipline.md` mandates a SERVER-SIDE revert as the
remedy for a red master that blocks its own repair, and
`check-red-green-replay` refused exactly that commit — because a
server-side revert carries no TDD trailers PRECISELY BECAUSE no local hook
mediates it, which is the property the directive requires it to have.

⛔ THE BOUNDARY IS TESTED IN BOTH DIRECTIONS, AND THAT IS THE POINT. An
exemption that admits everything revert-SHAPED would be worse than the
deadlock: it would restore the escape hatch `ci-gate-discipline.md` forbids
without exception, and any agent could produce one on demand. So every
positive test here is paired with a near-miss that must still be refused:

- a hand-authored revert dressed up with the same content, the same
  `This reverts commit <sha>.` body and a spoofed `GitHub
  <noreply@github.com>` committer, but no forge signature;
- a revert signed by a real OpenPGP key that is simply not the pinned one;
- a correctly-signed revert that also slips in one new product line;
- a correctly-signed revert naming a commit that is not on `origin/master`.

And the DISCRIMINATING CONTROL runs at the range gate itself: an ordinary
untrailered impl commit is still convicted after the change. Without that
leg the fix would be indistinguishable from disabling the check.

The trust root is swapped for an EPHEMERAL fixture key by passing
`trust_root=` in-process. That parameter is a test seam, not a lever —
there is no environment variable, config key or flag that reaches it, so
nothing here widens what the shipped check trusts.

IT ALSO PINS THE RETURN SHAPE (work-item livespec-dev-tooling-qndn.12).
The exemption reaches IO — `gpg --import`, `git verify-commit`, three
more git probes — so it is not total, and it answers on the `IOResult`
railway. Nothing in this repo's aggregate would notice that sliding back:
`checks/public_api_result_typed` is the check that reads the return
annotation and it is a no-op here, so the assertions below apply that
check's own terminal-name rule to the source directly, and the failure
track is inhabited end to end rather than left as an uninhabited type.
"""

from __future__ import annotations

import ast
import functools
import importlib.util
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from returns.io import IOFailure, IOResult
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.checks._red_green_replay_revert import (
    GITHUB_FORGE_TRUST_ROOT,
    RANGE_MISSING_TRAILERS_HINT,
    ForgeTrustRoot,
    _reverted_shas_from_message,
    _run,
    _undoes_ancestor,
    _validsig_names_trusted_key,
    is_forge_authored_revert,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from types import ModuleType

    # Typing-only, and deliberately so: a runtime import of the failure type
    # would make this file's Red leg a COLLECTION error against the pre-railway
    # module, which proves unimportability rather than the missing behavior.
    from livespec_dev_tooling.checks._red_green_replay_revert import ForgeProbeUnavailable

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECKS_DIR = _REPO_ROOT / "livespec_dev_tooling" / "checks"
_RED_GREEN_REPLAY = _CHECKS_DIR / "red_green_replay.py"

# The two names `checks/public_api_result_typed` accepts as railway-typed.
# Restated here rather than imported so this file pins the PROPERTY that check
# reads, independently of the check's own shape.
_RAILWAY_RETURN_NAMES = frozenset({"Result", "IOResult"})

# Vars git sets when invoking hooks; inherited by every child and would
# redirect the fixture repo's git calls at the SURROUNDING repository.
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

# The livespec-overseer file whose PLR0915 trip turned master red at
# 10:29:49Z on 2026-08-22, reproduced here as the product impl `.py` the
# revert has to restore.
_PRODUCT_PATH = "overseer/_supervisor_tick.py"
_PRE_REVERT_BODY = '"""Supervisor tick."""\n\n\ndef run_tick() -> int:\n    return 0\n'
_REDDENING_BODY = (
    '"""Supervisor tick."""\n\n\ndef run_tick() -> int:\n    extra = 1\n    return extra - 1\n'
)
_TRAILERED_MESSAGE = (
    "feat(supervisor): add statements to run_tick\n"
    "\n"
    "TDD-Red-Test-File-Checksum: sha256:aaaa\n"
    "TDD-Green-Verified-At: 2026-08-22T10:29:49Z\n"
)
_PYPROJECT = (
    "[tool.livespec_dev_tooling]\n"
    'source_trees = ["overseer"]\n'
    'source_tree_prefixes = ["overseer/"]\n'
)

_A_PINNED_FINGERPRINT = "968479A1AFF927E37D1A566BB5690EEEBB952194"


@dataclass(frozen=True, kw_only=True)
class ForgeKey:
    """An ephemeral OpenPGP key standing in for the forge's own signing key."""

    home: Path
    fingerprint: str
    trust_root: ForgeTrustRoot


@dataclass(frozen=True, kw_only=True)
class DeadlockRepo:
    """The 2026-08-22 range: `origin/master` at the reddening commit, one commit past it."""

    path: Path
    reddening_sha: str


def _terminal_return_name(*, rendered: str) -> str:
    """`IOResult[bool, ForgeProbeUnavailable]` → `IOResult`.

    Mirrors the reduction `public_api_result_typed` applies to a rendered
    return annotation before comparing it: drop the subscript, then drop any
    dotted qualifier.
    """
    return rendered.split("[", maxsplit=1)[0].rsplit(".", maxsplit=1)[-1]


@pytest.fixture(autouse=True)
def _scrub_git_hook_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _GIT_ENV_PASSTHROUGH_VARS:
        monkeypatch.delenv(var, raising=False)


def _gpg(*, home: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["gpg", "--batch", "--quiet", "--no-tty", *args],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "GNUPGHOME": str(home)},
    )


def _new_signing_key(*, uid: str) -> ForgeKey:
    """Generate a throwaway ed25519 signing key in its own GNUPGHOME."""
    home = Path(tempfile.mkdtemp(prefix="rgr-forge-key-"))
    _gpg(
        home=home,
        args=["--passphrase", "", "--quick-generate-key", uid, "ed25519", "sign", "0"],
    )
    listed = _gpg(home=home, args=["--with-colons", "--fingerprint", "--list-secret-keys"])
    fingerprint = next(
        line.split(":")[9] for line in listed.stdout.splitlines() if line.startswith("fpr:")
    )
    armored = _gpg(home=home, args=["--armor", "--export", fingerprint])
    return ForgeKey(
        home=home,
        fingerprint=fingerprint,
        trust_root=ForgeTrustRoot(fingerprints=(fingerprint,), public_key_block=armored.stdout),
    )


def _discard_signing_key(*, key: ForgeKey) -> None:
    _ = subprocess.run(
        ["gpgconf", "--homedir", str(key.home), "--kill", "all"],
        capture_output=True,
        check=False,
    )
    shutil.rmtree(key.home, ignore_errors=True)


@pytest.fixture(scope="session")
def forge_key() -> Iterator[ForgeKey]:
    """The key the fixture trust root pins — the stand-in for GitHub's web-flow key."""
    key = _new_signing_key(uid="Fixture Forge <forge@example.invalid>")
    yield key
    _discard_signing_key(key=key)


@pytest.fixture(scope="session")
def impostor_key() -> Iterator[ForgeKey]:
    """A real key that is simply NOT the pinned one — the forgery the exemption must refuse."""
    key = _new_signing_key(uid="Impostor <impostor@example.invalid>")
    yield key
    _discard_signing_key(key=key)


def _git(
    *, cwd: Path, args: list[str], home: Path | None = None, overrides: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k not in _GIT_ENV_PASSTHROUGH_VARS}
    if home is not None:
        env["GNUPGHOME"] = str(home)
    env.update(overrides or {})
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True, env=env
    )


def _head_sha(*, repo: Path) -> str:
    return _git(cwd=repo, args=["rev-parse", "HEAD"]).stdout.strip()


def _deadlock_repo(
    *, tmp_path: Path, forge_key: ForgeKey, monkeypatch: pytest.MonkeyPatch
) -> DeadlockRepo:
    """Rebuild the measured range: base, the reddening commit, `origin/master` pinned to it.

    Mirrors 2026-08-22 in livespec-overseer. The reddening commit is
    LEGALLY trailered — it is not what the gate objects to. What follows it
    on the branch is.

    Chdirs into the fixture, because the module under test takes no cwd
    argument: like every other git reader in this check it runs against the
    PROCESS cwd, since it is invoked by git in the repository being gated.
    """
    repo = tmp_path / "overseer"
    (repo / "overseer").mkdir(parents=True)
    _git(cwd=repo.parent, args=["init", "-q", str(repo)])
    for key, value in (
        ("user.email", "test@example.com"),
        ("user.name", "Test"),
        ("commit.gpgsign", "false"),
        ("gpg.program", "gpg"),
        ("user.signingkey", forge_key.fingerprint),
    ):
        _git(cwd=repo, args=["config", key, value])
    (repo / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    (repo / _PRODUCT_PATH).write_text(_PRE_REVERT_BODY, encoding="utf-8")
    _git(cwd=repo, args=["add", "-A"])
    _git(cwd=repo, args=["commit", "-qm", "chore: base"])
    (repo / _PRODUCT_PATH).write_text(_REDDENING_BODY, encoding="utf-8")
    _git(cwd=repo, args=["add", "-A"])
    _git(cwd=repo, args=["commit", "-qm", _TRAILERED_MESSAGE])
    reddening = _head_sha(repo=repo)
    _git(cwd=repo, args=["update-ref", "refs/remotes/origin/master", "HEAD"])
    monkeypatch.chdir(repo)
    return DeadlockRepo(path=repo, reddening_sha=reddening)


def _revert(
    *,
    deadlock: DeadlockRepo,
    key: ForgeKey | None,
    overrides: dict[str, str] | None = None,
) -> str:
    """Revert the reddening commit — signed by `key`, or unsigned when `key` is None."""
    sign = [f"--gpg-sign={key.fingerprint}"] if key is not None else ["--no-gpg-sign"]
    _git(
        cwd=deadlock.path,
        args=["revert", "--no-edit", *sign, deadlock.reddening_sha],
        home=key.home if key is not None else None,
        overrides=overrides,
    )
    return _head_sha(repo=deadlock.path)


def _exemption(*, sha: str, key: ForgeKey) -> IOResult[bool, ForgeProbeUnavailable]:
    """Ask the exemption about `sha` in the CURRENT cwd — the fixture repo."""
    return is_forge_authored_revert(
        sha=sha,
        product_paths=[_PRODUCT_PATH],
        base_ref="origin/master",
        trust_root=key.trust_root,
    )


def _is_exempt(*, sha: str, key: ForgeKey) -> bool:
    """The MEASURED verdict — unwrapped, so a probe that could not run is an error here.

    Every caller below is asking about a repository where both binaries are
    present, so the success track is the assertion these tests mean to make;
    the failure track has its own test rather than being folded into `False`.
    """
    return unsafe_perform_io(_exemption(sha=sha, key=key).unwrap())


def _bin_dir_with_git_only(*, tmp_path: Path) -> Path:
    """A PATH entry carrying `git` and nothing else — the absent-`gpg` CI image.

    The condition the range gate's remedy hint already names ("check that
    `gpg` is on PATH in this environment"), built rather than described: `git`
    keeps working, so the range validator's own probes still run and the ONLY
    thing that cannot start is the exemption's signature check.
    """
    bin_dir = tmp_path / "bin-git-only"
    bin_dir.mkdir()
    git = shutil.which("git")
    assert git is not None
    (bin_dir / "git").symlink_to(git)
    return bin_dir


# ---------------------------------------------------------------------------
# The trust root itself — what the exemption keys on.
# ---------------------------------------------------------------------------


def test_shipped_trust_root_pins_githubs_own_web_flow_keys() -> None:
    """The shipped pin is key MATERIAL plus fingerprints, not a subject-line rule.

    Both of GitHub's web-flow keys are pinned: B5690EEEBB952194 (in service
    since the 2024-01-16 rotation) and 4AEE18F83AFDEB23 (retained so history
    authored before it reads the same way).
    """
    assert _A_PINNED_FINGERPRINT in GITHUB_FORGE_TRUST_ROOT.fingerprints
    assert "5DE3E0509C47EA3CF04A42D34AEE18F83AFDEB23" in GITHUB_FORGE_TRUST_ROOT.fingerprints
    assert GITHUB_FORGE_TRUST_ROOT.public_key_block.count("BEGIN PGP PUBLIC KEY BLOCK") == 2


def test_range_hint_names_the_precondition_and_the_reachable_path() -> None:
    """The remedy hint no longer prescribes a route a red master forbids.

    Criterion 5 of livespec-dev-tooling-j2qa: the old text sent the operator
    to re-author locally and force-push without saying that
    `check-master-ci-green`, inside the same `check:` aggregate the push
    runs, refuses that push while master is red.
    """
    assert "check-master-ci-green" in RANGE_MISSING_TRAILERS_HINT
    assert "SERVER-SIDE" in RANGE_MISSING_TRAILERS_HINT
    assert "ci-gate-discipline.md" in RANGE_MISSING_TRAILERS_HINT


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("[GNUPG:] GOODSIG 2B31E19453E2B8BD GitHub <noreply@github.com>", False),
        (f"[GNUPG:] VALIDSIG {_A_PINNED_FINGERPRINT} 2026-08-22 0 0 4 0 22 10 00", True),
        ("[GNUPG:] VALIDSIG 0000000000000000000000000000000000000000 2026-08-22", False),
    ],
)
def test_only_a_validsig_naming_a_pinned_fingerprint_counts(*, line: str, expected: bool) -> None:
    """`GOODSIG` alone is not enough, and a `VALIDSIG` by another key is not enough."""
    assert (
        _validsig_names_trusted_key(line=line, fingerprints=GITHUB_FORGE_TRUST_ROOT.fingerprints)
        is expected
    )


def test_unimportable_trust_root_material_grants_no_exemption(*, tmp_path: Path) -> None:
    """Unusable key material fails CLOSED — the gate keeps its ordinary verdict.

    On the SUCCESS track, deliberately: gpg ran and refused the material, which
    is a measurement. Only a gpg that could not be started at all is a
    non-answer.
    """
    key = ForgeKey(
        home=tmp_path,
        fingerprint="0" * 40,
        trust_root=ForgeTrustRoot(
            fingerprints=("0" * 40,), public_key_block="not an OpenPGP key block\n"
        ),
    )
    assert not _is_exempt(sha="HEAD", key=key)


def test_is_forge_authored_revert_declares_a_railway_return_annotation() -> None:
    """The SOURCE annotation is what the shipped detector reads.

    Asserted against the source rather than the runtime value because that is
    the surface `public_api_result_typed` judges — an annotation reverted to a
    bare `bool` while the body still happened to return a container would
    satisfy a runtime check and fail the real one.
    """
    source = (_CHECKS_DIR / "_red_green_replay_revert.py").read_text(encoding="utf-8")
    functions = {
        node.name: node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef)
    }
    annotation = functions["is_forge_authored_revert"].returns
    assert annotation is not None
    rendered = ast.unparse(annotation)
    assert _terminal_return_name(rendered=rendered) in _RAILWAY_RETURN_NAMES, rendered


def test_unstartable_binary_takes_the_failure_track() -> None:
    """A binary that cannot be STARTED is no longer spelled as an exit code.

    It used to arrive as a synthetic 127, indistinguishable from a probe that
    ran and refused; the argv and the OS's own reason are what the range gate
    can now report instead of guessing.
    """
    probed = _run(argv=["livespec-dev-tooling-no-such-binary"])

    assert isinstance(probed, IOFailure)
    unavailable = unsafe_perform_io(probed.failure())
    assert unavailable.argv == "livespec-dev-tooling-no-such-binary"
    assert unavailable.detail != ""


# ---------------------------------------------------------------------------
# The exemption boundary, tested in BOTH directions.
# ---------------------------------------------------------------------------


def test_genuine_forge_signed_revert_of_an_ancestor_is_exempt(
    *, tmp_path: Path, forge_key: ForgeKey, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PR 1630's shape: a forge-signed revert restoring already-gated bytes passes."""
    deadlock = _deadlock_repo(tmp_path=tmp_path, forge_key=forge_key, monkeypatch=monkeypatch)
    revert_sha = _revert(deadlock=deadlock, key=forge_key)
    assert _is_exempt(sha=revert_sha, key=forge_key)


def test_hand_authored_revert_lookalike_is_still_refused(
    *, tmp_path: Path, forge_key: ForgeKey, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same content, same `This reverts commit` body, spoofed committer — no signature.

    This is the forgery the exemption exists to refuse. Every property an
    agent CAN produce is present; the one it cannot is absent.
    """
    deadlock = _deadlock_repo(tmp_path=tmp_path, forge_key=forge_key, monkeypatch=monkeypatch)
    lookalike = _revert(
        deadlock=deadlock,
        key=None,
        overrides={"GIT_COMMITTER_NAME": "GitHub", "GIT_COMMITTER_EMAIL": "noreply@github.com"},
    )
    assert not _is_exempt(sha=lookalike, key=forge_key)


def test_revert_signed_by_an_unpinned_key_is_still_refused(
    *,
    tmp_path: Path,
    forge_key: ForgeKey,
    impostor_key: ForgeKey,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real, cryptographically valid signature by the WRONG key buys nothing."""
    deadlock = _deadlock_repo(tmp_path=tmp_path, forge_key=forge_key, monkeypatch=monkeypatch)
    signed_by_impostor = _revert(deadlock=deadlock, key=impostor_key)
    assert not _is_exempt(sha=signed_by_impostor, key=forge_key)


def test_signed_revert_that_also_adds_product_content_is_refused(
    *, tmp_path: Path, forge_key: ForgeKey, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Byte-identity with the reverted commit's parent is what bounds the exemption.

    A commit that undoes the reddening change AND slips in one new product
    line is not restoring already-gated state, so it is refused even though
    its signature and its `This reverts commit` line are both genuine.
    """
    deadlock = _deadlock_repo(tmp_path=tmp_path, forge_key=forge_key, monkeypatch=monkeypatch)
    _revert(deadlock=deadlock, key=forge_key)
    (deadlock.path / _PRODUCT_PATH).write_text(
        _PRE_REVERT_BODY + "\n\ndef smuggled() -> int:\n    return 1\n", encoding="utf-8"
    )
    _git(cwd=deadlock.path, args=["add", "-A"])
    _git(
        cwd=deadlock.path,
        args=["commit", "-q", "--amend", "--no-edit", f"--gpg-sign={forge_key.fingerprint}"],
        home=forge_key.home,
    )
    assert not _is_exempt(sha=_head_sha(repo=deadlock.path), key=forge_key)


def test_signed_revert_naming_a_commit_absent_from_master_is_refused(
    *, tmp_path: Path, forge_key: ForgeKey, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reverted commit must be an ANCESTOR of `origin/master`, not merely reachable.

    Reverting a commit invented on the branch restores bytes no gate ever
    admitted, so the evidence-transfer argument does not hold for it.
    """
    deadlock = _deadlock_repo(tmp_path=tmp_path, forge_key=forge_key, monkeypatch=monkeypatch)
    (deadlock.path / _PRODUCT_PATH).write_text(_PRE_REVERT_BODY + "# branch-only\n", "utf-8")
    _git(cwd=deadlock.path, args=["add", "-A"])
    _git(cwd=deadlock.path, args=["commit", "-qm", "chore: branch-only change"])
    branch_only = _head_sha(repo=deadlock.path)
    _git(
        cwd=deadlock.path,
        args=["revert", "--no-edit", f"--gpg-sign={forge_key.fingerprint}", branch_only],
        home=forge_key.home,
    )
    assert not _is_exempt(sha=_head_sha(repo=deadlock.path), key=forge_key)


def test_signed_commit_naming_no_reverted_commit_is_refused(
    *, tmp_path: Path, forge_key: ForgeKey, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A forge signature alone is not the exemption — the content relation is half of it."""
    deadlock = _deadlock_repo(tmp_path=tmp_path, forge_key=forge_key, monkeypatch=monkeypatch)
    (deadlock.path / _PRODUCT_PATH).write_text(_PRE_REVERT_BODY, encoding="utf-8")
    _git(cwd=deadlock.path, args=["add", "-A"])
    _git(
        cwd=deadlock.path,
        args=["commit", "-qm", "fix: undo by hand", f"--gpg-sign={forge_key.fingerprint}"],
        home=forge_key.home,
    )
    assert not _is_exempt(sha=_head_sha(repo=deadlock.path), key=forge_key)


def test_message_of_an_unreadable_commit_names_nothing(*, tmp_path: Path) -> None:
    """A git that RAN and could not read the object names no candidates.

    On the success track: an object that is not there is an answer, and the
    empty tuple is what that answer looks like. The failure track is reserved
    for a git that never ran.
    """
    repo = tmp_path / "empty"
    repo.mkdir()
    _git(cwd=repo.parent, args=["init", "-q", str(repo)])
    assert unsafe_perform_io(_reverted_shas_from_message(sha="0" * 40).unwrap()) == ()


def test_a_root_commit_is_not_an_undo_of_anything(
    *, tmp_path: Path, forge_key: ForgeKey, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The single-parent requirement, and the unreadable-object arm beside it."""
    deadlock = _deadlock_repo(tmp_path=tmp_path, forge_key=forge_key, monkeypatch=monkeypatch)
    monkeypatch.chdir(deadlock.path)
    root = _git(cwd=deadlock.path, args=["rev-list", "--max-parents=0", "HEAD"]).stdout.strip()
    reverted, base_ref, paths = deadlock.reddening_sha, "origin/master", [_PRODUCT_PATH]
    for sha in (root, "0" * 40):
        undone = _undoes_ancestor(
            sha=sha, reverted=reverted, base_ref=base_ref, product_paths=paths
        )
        assert not unsafe_perform_io(undone.unwrap())


def test_an_unstartable_gpg_answers_on_the_failure_track(
    *, tmp_path: Path, forge_key: ForgeKey, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same revert that IS exempt above answers "not measured" with no `gpg`.

    That pairing is the whole point of the conversion: the commit has not
    changed, so a `False` here would be a claim about the commit that nothing
    established. The verdict the caller draws from it is still no-exemption —
    see the range-gate leg below — but the gate can now name the invocation
    instead of guessing at it.
    """
    deadlock = _deadlock_repo(tmp_path=tmp_path, forge_key=forge_key, monkeypatch=monkeypatch)
    revert_sha = _revert(deadlock=deadlock, key=forge_key)
    monkeypatch.setenv("PATH", str(_bin_dir_with_git_only(tmp_path=tmp_path)))

    probed = _exemption(sha=revert_sha, key=forge_key)

    assert isinstance(probed, IOFailure)
    unavailable = unsafe_perform_io(probed.failure())
    assert unavailable.argv.startswith("gpg ")


# ---------------------------------------------------------------------------
# Criterion 6 — the deadlock pinned shut at the range gate, with criterion 3's
# discriminating control beside it.
# ---------------------------------------------------------------------------


def _load_range_validator(*, forge_key: ForgeKey, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Load `red_green_replay` with the fixture key standing in for the pinned one.

    Only the KEYRING is swapped: the real `is_forge_authored_revert` runs,
    bound to the fixture trust root through a partial. Nothing about the
    ancestry or byte-identity legs is stubbed.
    """
    spec = importlib.util.spec_from_file_location("rgr_range", str(_RED_GREEN_REPLAY))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(
        module,
        "is_forge_authored_revert",
        functools.partial(is_forge_authored_revert, trust_root=forge_key.trust_root),
        raising=False,
    )
    return module


def test_measured_2026_08_22_range_passes_for_the_server_side_revert(
    *, tmp_path: Path, forge_key: ForgeKey, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PR 1630's range reaches a PASSING verdict — the deadlock's server-side exit reopens.

    The fixture is the measured instance: `origin/master` at the reddening
    commit (master CI red from 10:29:49Z), one forge-authored revert commit
    past it carrying no TDD trailers and touching product impl `.py`. Before
    this change that range failed `red-green-replay-range-missing-trailers`
    at 11:18:01Z.
    """
    deadlock = _deadlock_repo(tmp_path=tmp_path, forge_key=forge_key, monkeypatch=monkeypatch)
    _revert(deadlock=deadlock, key=forge_key)
    module = _load_range_validator(forge_key=forge_key, monkeypatch=monkeypatch)
    monkeypatch.chdir(deadlock.path)
    assert module._validate_range() == 0  # noqa: SLF001 — the module's own range entry point.


def test_measured_2026_08_22_range_still_convicts_an_ordinary_untrailered_commit(
    *, tmp_path: Path, forge_key: ForgeKey, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The discriminating control: the gate still does its job after the change.

    Same repo, same red master, same product file — but an ordinary
    untrailered impl commit rather than a forge-authored revert. It is
    convicted, which is what separates this fix from disabling the check.
    """
    deadlock = _deadlock_repo(tmp_path=tmp_path, forge_key=forge_key, monkeypatch=monkeypatch)
    (deadlock.path / _PRODUCT_PATH).write_text(_PRE_REVERT_BODY + "# hand edit\n", "utf-8")
    _git(cwd=deadlock.path, args=["add", "-A"])
    _git(cwd=deadlock.path, args=["commit", "-qm", "fix: hand-edit the supervisor tick"])
    module = _load_range_validator(forge_key=forge_key, monkeypatch=monkeypatch)
    monkeypatch.chdir(deadlock.path)
    assert module._validate_range() == 1  # noqa: SLF001 — the module's own range entry point.


def test_range_gate_convicts_and_names_an_exemption_it_could_not_probe(
    *,
    tmp_path: Path,
    forge_key: ForgeKey,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The caller CONSUMES the failure track: same range, convicted, and said out loud.

    Byte-for-byte the passing range above — a genuine forge-authored revert —
    with `gpg` removed from PATH. The verdict is the strict one the exemption
    has always given when it could not establish itself, which is why this
    conversion cannot widen the gate. What is new is the diagnostic naming the
    invocation that could not start, in place of a hint guessing at it.
    """
    deadlock = _deadlock_repo(tmp_path=tmp_path, forge_key=forge_key, monkeypatch=monkeypatch)
    _revert(deadlock=deadlock, key=forge_key)
    module = _load_range_validator(forge_key=forge_key, monkeypatch=monkeypatch)
    monkeypatch.chdir(deadlock.path)
    monkeypatch.setenv("PATH", str(_bin_dir_with_git_only(tmp_path=tmp_path)))

    assert module._validate_range() == 1  # noqa: SLF001 — the module's own range entry point.

    reported = capsys.readouterr().err
    assert "red-green-replay-forge-exemption-unprobed" in reported
    assert "red-green-replay-range-missing-trailers" in reported

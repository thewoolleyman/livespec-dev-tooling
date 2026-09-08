"""Outside-in test for `livespec_dev_tooling/install_github_rate_limit_decision.py`.

The installer writes the canonical GitHub rate-limit DECISION body into a
Driver plugin bundle's hooks directory. Mirrors
`test_install_no_shadow_ledger.py`'s embedding-integrity and round-trip
coverage, adapted for the profile auto-detect this body resolves its
destination through instead of a role key.

Three concerns are covered here, and only the first is transcription hygiene:

1. EMBEDDING INTEGRITY — the constant compiles, carries the shebang, and
   exports the decision surface a Driver imports. These guarantee the
   hook-file → constant transcription was not corrupted.
2. THE STDLIB-ONLY CONTRACT — asserted mechanically over the body's own AST
   rather than trusted. The guard fires under bare system `python3` before any
   virtualenv exists, so a single `import structlog` in the body would wedge
   every governed repo's Bash tool at the moment the hook is installed, and it
   would do so at the FIRST invocation rather than at any gate here.
3. THE REPLAY CORPUS — the measured regression population, replayed against
   the canonical body itself.

The corpus fixture is a BYTE-IDENTICAL copy of
`livespec-driver-claude`'s `tests/hooks/fixtures/
github_rate_limit_guard_replay_corpus.json`, the committed successor to the
session-scratch harness that measured a 40.5% false-positive rate over 73,162
real Bash commands. That Driver replays it through its own hook BOUNDARY (exit
status), which is what proves a governed repo sees the verdict; this module
replays the same vectors through the pure DECISION FUNCTION, which is what
proves the hoisted body — the one every future Driver will consume — carries
the fix rather than merely sitting next to it. The two are complementary: a
port to Codex or pi cannot be byte-identical to the Claude hook's protocol
half, so the corpus is the one shared thing every runtime conforms to.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from livespec_dev_tooling import install_github_rate_limit_decision as _installer
from livespec_dev_tooling.install_github_rate_limit_decision import (
    CANONICAL_GITHUB_RATE_LIMIT_DECISION_BODY,
    DECISION_BODY_FILENAME,
    driver_decision_body_path,
    main,
)

if TYPE_CHECKING:
    from types import ModuleType

__all__: list[str] = []


_CORPUS_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "github_rate_limit_guard_replay_corpus.json"
)
# The four buckets the 7-day measurement actually partitioned its denials into.
# `b4` was carved out of the true-positive population AFTERWARDS, so it carries
# no measured count and stays out of the baseline arithmetic.
_MEASURED_BUCKETS = frozenset({"tp", "b1", "b2", "b3"})
# The ONLY imports the body may carry. `__future__` is the annotations import
# every module here opens with; `re` is the whole of its machinery.
_ALLOWED_BODY_IMPORTS = frozenset({"__future__", "re"})
# The public surface a Driver's protocol wrapper imports. Private names cannot
# cross a module boundary, so the hoist promoted exactly these four functions
# and the rule-name constants that a verdict record carries.
_EXPECTED_BODY_EXPORTS = frozenset(
    {
        "LOOP_MUTATION_RULE",
        "LOOP_READ_RULE",
        "MAX_LITERAL_ITERATIONS",
        "SLEEP_READ_RULE",
        "gh_at_command_position",
        "has_cached_gh_api",
        "mask_command",
        "matched_rule",
    }
)


def _claude_bundle(*, root: Path) -> Path:
    """Make `root` read as a CLAUDE Driver bundle to the profile auto-detect."""
    manifest = root / ".claude-plugin" / "plugin.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    _ = manifest.write_text('{"name": "livespec"}\n', encoding="utf-8")
    return root / ".claude-plugin" / "hooks" / DECISION_BODY_FILENAME


def _codex_bundle(*, root: Path) -> Path:
    """Make `root` read as a CODEX Driver bundle to the profile auto-detect."""
    manifest = root / ".agents" / "plugins" / "marketplace.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    _ = manifest.write_text('{"name": "livespec-driver-codex"}\n', encoding="utf-8")
    return root / "livespec" / "hooks" / DECISION_BODY_FILENAME


# --- embedding integrity ---------------------------------------------------


def test_canonical_body_compiles_as_valid_python() -> None:
    """The embedded constant is syntactically valid Python (transcription proof)."""
    _ = compile(CANONICAL_GITHUB_RATE_LIMIT_DECISION_BODY, "<body>", "exec")


def test_canonical_body_starts_with_the_shebang_and_ends_with_a_newline() -> None:
    """The constant carries the shebang head and no truncated tail."""
    assert CANONICAL_GITHUB_RATE_LIMIT_DECISION_BODY.startswith("#!/usr/bin/env python3\n")
    assert CANONICAL_GITHUB_RATE_LIMIT_DECISION_BODY.endswith("\n")


def test_canonical_body_carries_the_decision_pair_and_no_hook_protocol() -> None:
    """The body is the DECISION half only — the protocol half stays per-Driver.

    A body that swallowed the hook protocol would make the Codex and pi ports
    conform to Claude's stdin/exit-2 contract, which is precisely the coupling
    the seam exists to avoid.
    """
    assert "def mask_command(*, command: str) -> str:" in CANONICAL_GITHUB_RATE_LIMIT_DECISION_BODY
    assert (
        "def matched_rule(*, masked: str) -> str | None:"
        in CANONICAL_GITHUB_RATE_LIMIT_DECISION_BODY
    )
    assert "sys.stdin" not in CANONICAL_GITHUB_RATE_LIMIT_DECISION_BODY
    assert "emit_verdict" not in CANONICAL_GITHUB_RATE_LIMIT_DECISION_BODY
    assert "__main__" not in CANONICAL_GITHUB_RATE_LIMIT_DECISION_BODY


def test_canonical_body_imports_only_the_standard_library() -> None:
    """The hard constraint, asserted over the body's AST rather than trusted.

    The guard runs under bare system `python3` with no virtualenv and no
    third-party packages — it fires before any venv exists. An import of
    `livespec_runtime`, of a vendored package, or of a sibling that is not
    shipped beside it would not fail here; it would fail at the first Bash call
    in every governed repo, which is the failure this assertion buys out.
    """
    tree = ast.parse(CANONICAL_GITHUB_RATE_LIMIT_DECISION_BODY)
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            roots.add((node.module or "").split(".")[0])
    assert roots == _ALLOWED_BODY_IMPORTS


def test_canonical_body_exports_the_public_decision_surface(*, tmp_path: Path) -> None:
    """Rendered and imported, the body exposes exactly the names a Driver consumes."""
    module = _render_decision_module(root=tmp_path)
    assert frozenset(module.__all__) == _EXPECTED_BODY_EXPORTS
    for name in sorted(_EXPECTED_BODY_EXPORTS):
        assert hasattr(module, name)


def _render_decision_module(*, root: Path) -> ModuleType:
    """Import the canonical body as a real module, exactly as a Driver would.

    Rendered to a file and imported rather than `exec`'d into a namespace so
    the body is exercised through the SAME mechanism a Driver's hook uses — an
    ordinary module import off the hooks directory.
    """
    path = root / DECISION_BODY_FILENAME
    _ = path.write_text(CANONICAL_GITHUB_RATE_LIMIT_DECISION_BODY, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("github_rate_limit_decision_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def decision(*, tmp_path_factory: pytest.TempPathFactory) -> ModuleType:
    """The canonical body, imported once for the whole replay."""
    return _render_decision_module(root=tmp_path_factory.mktemp("decision"))


# --- destination resolution ------------------------------------------------


def test_driver_decision_body_path_resolves_the_claude_bundle(*, tmp_path: Path) -> None:
    """A `.claude-plugin/plugin.json` root resolves to the claude hooks directory."""
    expected = _claude_bundle(root=tmp_path)
    assert driver_decision_body_path(project_root=tmp_path) == expected


def test_driver_decision_body_path_resolves_the_codex_bundle(*, tmp_path: Path) -> None:
    """An `.agents/plugins/marketplace.json` root resolves to the codex hooks directory."""
    expected = _codex_bundle(root=tmp_path)
    assert driver_decision_body_path(project_root=tmp_path) == expected


def test_driver_decision_body_path_is_none_off_a_driver_tree(*, tmp_path: Path) -> None:
    """A tree with no Driver manifest resolves to nothing at all.

    The self-skip is load-bearing: livespec core, the orchestrator plugins and
    this library itself carry no Driver manifest, and a body installed into one
    of them would be a file nothing loads.
    """
    assert driver_decision_body_path(project_root=tmp_path) is None


# --- install round trip (via main()) ---------------------------------------


def test_main_writes_the_canonical_body_into_a_claude_bundle(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The claude profile → the installer writes the exact canonical bytes."""
    destination = _claude_bundle(root=tmp_path)
    monkeypatch.chdir(tmp_path)

    rc = main()

    assert rc == 0
    assert destination.read_text(encoding="utf-8") == CANONICAL_GITHUB_RATE_LIMIT_DECISION_BODY


def test_main_writes_the_canonical_body_into_a_codex_bundle(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The codex profile → the same bytes, at that bundle's own hooks directory."""
    destination = _codex_bundle(root=tmp_path)
    monkeypatch.chdir(tmp_path)

    rc = main()

    assert rc == 0
    assert destination.read_text(encoding="utf-8") == CANONICAL_GITHUB_RATE_LIMIT_DECISION_BODY


def test_main_no_ops_off_a_driver_tree(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No Driver manifest → the installer writes nothing and returns 0."""
    monkeypatch.chdir(tmp_path)

    rc = main()

    assert rc == 0
    assert list(tmp_path.iterdir()) == []


def test_main_is_idempotent(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Re-running the installer overwrites with the identical canonical body."""
    destination = _claude_bundle(root=tmp_path)
    monkeypatch.chdir(tmp_path)

    assert main() == 0
    first = destination.read_text(encoding="utf-8")
    assert main() == 0
    second = destination.read_text(encoding="utf-8")

    assert first == second == CANONICAL_GITHUB_RATE_LIMIT_DECISION_BODY


def test_module_importable_without_running_main() -> None:
    """The module imports cleanly (covers the `__name__ != '__main__'` branch)."""
    spec = importlib.util.spec_from_file_location(
        "install_github_rate_limit_decision_import_test", str(Path(_installer.__file__))
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main)


# ---------------------------------------------------------------------------
# Replay corpus — the measured regression population, replayed against the
# canonical body. See the module docstring for how this differs from the
# Driver's own boundary replay of the same fixture.
# ---------------------------------------------------------------------------


def _mapping(*, value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return cast("dict[str, object]", value)


def _text(*, mapping: dict[str, object], key: str) -> str:
    value = mapping[key]
    assert isinstance(value, str)
    return value


def _whole_number(*, mapping: dict[str, object], key: str) -> int:
    value = mapping[key]
    assert isinstance(value, int)
    return value


def _percentage(*, mapping: dict[str, object], key: str) -> float:
    value = mapping[key]
    assert isinstance(value, float)
    return value


def _measured_denials(*, bucket: dict[str, object]) -> int | None:
    """The bucket's share of the measured denial population, or None when it has none."""
    value = bucket["measured_denials"]
    if value is None:
        return None
    assert isinstance(value, int)
    return value


_CORPUS = _mapping(value=json.loads(_CORPUS_PATH.read_text(encoding="utf-8")))
_CORPUS_MEASUREMENT = _mapping(value=_CORPUS["measurement"])
_CORPUS_BASELINE = _mapping(value=_CORPUS["pre_fix_baseline"])
_CORPUS_BUCKETS = {
    name: _mapping(value=bucket) for name, bucket in _mapping(value=_CORPUS["buckets"]).items()
}
# Credential shapes and session identifiers. The fixture is a REDACTED corpus
# of command SHAPES; raw transcript text would carry all of these.
_SECRET_SHAPES: tuple[str, ...] = (
    r"gh[pousr]_[A-Za-z0-9]{4}",
    r"github_pat_",
    r"authorization\s*:",
    r"bearer\s+[A-Za-z0-9]",
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
)
_UNREDACTED_SECRET = re.compile("|".join(_SECRET_SHAPES), re.IGNORECASE)
# An absolute path rooted in a home directory or a checkout root is repo-private
# even when it carries no secret: it names whose machine the command ran on.
_UNREDACTED_PRIVATE_PATH = re.compile(
    r"(?:^|[^\w.])(?:~/|\$HOME|/(?:Users|home|root|data|repos|mnt|workspace)/)",
    re.MULTILINE,
)


@dataclass(frozen=True, kw_only=True)
class ReplayVector:
    """One command shape, the verdict it must earn, and what the pre-fix build did."""

    identifier: str
    bucket: str
    expected_verdict: str
    pre_fix_verdict: str
    command: str


def _replay_vectors() -> list[ReplayVector]:
    raw = _CORPUS["vectors"]
    assert isinstance(raw, list)
    entries = [_mapping(value=entry) for entry in cast("list[object]", raw)]
    return [
        ReplayVector(
            identifier=_text(mapping=entry, key="id"),
            bucket=_text(mapping=entry, key="bucket"),
            expected_verdict=_text(mapping=entry, key="expected_verdict"),
            pre_fix_verdict=_text(mapping=entry, key="pre_fix_verdict"),
            command=_text(mapping=entry, key="command"),
        )
        for entry in entries
    ]


_REPLAY_VECTORS = _replay_vectors()


def _observed_verdict(*, decision: ModuleType, vector: ReplayVector) -> str:
    """Replay one vector through the canonical decision pair and name what it did."""
    rule = decision.matched_rule(masked=decision.mask_command(command=vector.command))
    return "allow" if rule is None else "deny"


@pytest.mark.parametrize(
    "vector", [pytest.param(vector, id=vector.identifier) for vector in _REPLAY_VECTORS]
)
def test_replay_corpus_vector_returns_its_recorded_verdict(
    *, decision: ModuleType, vector: ReplayVector
) -> None:
    assert _observed_verdict(decision=decision, vector=vector) == vector.expected_verdict


def test_replayed_corpus_has_no_false_positives_and_no_disabled_controls(
    *, decision: ModuleType
) -> None:
    """The gate: every false-positive vector allows WHILE every control still denies.

    Both halves are load-bearing. The first is the defect this corpus was cut
    to measure; the second is the control proving a green fixture came from a
    fixed body rather than a switched-off one — a hoist that dropped the
    decision logic on the way across would satisfy the first half alone.
    """
    observed = {
        vector.identifier: _observed_verdict(decision=decision, vector=vector)
        for vector in _REPLAY_VECTORS
    }
    allow_vectors = [v for v in _REPLAY_VECTORS if v.expected_verdict == "allow"]
    deny_vectors = [v for v in _REPLAY_VECTORS if v.expected_verdict == "deny"]
    assert allow_vectors
    assert deny_vectors
    false_positives = [v.identifier for v in allow_vectors if observed[v.identifier] == "deny"]
    not_denied = [v.identifier for v in deny_vectors if observed[v.identifier] == "allow"]
    assert 100 * len(false_positives) / len(allow_vectors) == 0.0, false_positives
    assert 100 * len(not_denied) / len(deny_vectors) == 0.0, not_denied


def test_replay_corpus_covers_every_measured_bucket() -> None:
    """Each bucket the measurement partitioned denials into carries a vector.

    A corpus that covers only the buckets a given fix touched would go green
    against a body that had regressed in one of the others.
    """
    covered = {vector.bucket for vector in _REPLAY_VECTORS}
    assert covered >= _MEASURED_BUCKETS
    assert covered == set(_CORPUS_BUCKETS)


def test_replay_corpus_vectors_agree_with_their_bucket_verdict() -> None:
    """A vector's expected verdict is the verdict its whole bucket is labelled with."""
    for vector in _REPLAY_VECTORS:
        bucket = _CORPUS_BUCKETS[vector.bucket]
        assert vector.expected_verdict == _text(mapping=bucket, key="expected_verdict")


def test_measured_false_positive_rate_is_reproducible_from_the_recorded_buckets() -> None:
    """The 40.5% figure must be derivable from the counts the fixture carries.

    A bare percentage in a plan note cannot be checked; per-bucket counts that
    sum to the recorded denial total, with the false share divided out of it,
    can. This is the arithmetic the gate above is measured against, and it is
    also what proves this vendored copy of the fixture is the measured one.
    """
    denials = {
        name: count
        for name, bucket in _CORPUS_BUCKETS.items()
        if (count := _measured_denials(bucket=bucket)) is not None
    }
    assert set(denials) == _MEASURED_BUCKETS
    total = sum(denials.values())
    assert total == _whole_number(mapping=_CORPUS_MEASUREMENT, key="denials")
    false = sum(
        count
        for name, count in denials.items()
        if _text(mapping=_CORPUS_BUCKETS[name], key="expected_verdict") == "allow"
    )
    recorded = _percentage(mapping=_CORPUS_MEASUREMENT, key="false_positive_rate_percent")
    assert round(100 * false / total, 1) == recorded


def test_replay_corpus_retains_every_vector_the_pre_fix_build_got_wrong() -> None:
    """The corpus keeps its regression value only while it still holds the failures.

    Each vector records what the pre-fix build returned for it. Dropping one —
    the cheapest way to make a stubborn fixture green — moves this count.
    """
    wrong = [v.identifier for v in _REPLAY_VECTORS if v.pre_fix_verdict != v.expected_verdict]
    assert len(wrong) == _whole_number(mapping=_CORPUS_BASELINE, key="vectors_wrong"), wrong


def test_replay_corpus_carries_no_credentials_session_ids_or_private_paths() -> None:
    """Redaction is a property of the FILE, not just of the command strings.

    Notes and provenance lines are prose written by hand, so they leak as
    easily as a command would; the whole fixture text is scanned.
    """
    text = _CORPUS_PATH.read_text(encoding="utf-8")
    assert _UNREDACTED_SECRET.search(text) is None
    assert _UNREDACTED_PRIVATE_PATH.search(text) is None

"""Tests for the canonical shell-quality policy check.

Covers the check module and both of its private halves — the recipe policy in
`_shell_quality_recipes` and, since livespec-dev-tooling-qndn.13, the
`just --dump` acquisition split out of it into `_shell_quality_dump`. The
private halves are tested from here rather than from mirrored files of their
own, matching how `_shell_quality_bashisms` and `_shell_quality_finding` are
already covered: `tests/` mirrors the check SLUG, and these modules are that
one check's interior.

Those new tests also pin the acquisition's RETURN SHAPE. Obtaining the dump
runs `just` in the repo under judgement, so it is not total, and it now
answers on the `IOResult` railway. Nothing in this repo's aggregate would
notice that sliding back: `checks/public_api_result_typed` is the check that
reads the return annotation and it is a no-op here (`pure_trees` is
`not_applicable`), so the assertions below apply that check's own
terminal-name rule directly, and each of the three ways to lose the dump is
inhabited rather than left uninhabited.
"""

from __future__ import annotations

import ast
import importlib
import os
import stat
import subprocess
from pathlib import Path

import pytest
from returns.pipeline import is_successful
from returns.primitives.exceptions import UnwrapFailedError
from returns.result import Failure
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.install_worktree_pack import CANONICAL_WORKTREE_JUST_BODY
from livespec_dev_tooling.shellcheck import (
    ShellCheckUnavailable,
    ShellCorpusEmpty,
    run_shellcheck,
)

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECKS_DIR = _REPO_ROOT / "livespec_dev_tooling" / "checks"
_CHECK_PATH = _CHECKS_DIR / "shell_quality.py"
_DUMP_MODULE_PATH = _CHECKS_DIR / "_shell_quality_dump.py"
_POLICY_MODULE_PATH = _CHECKS_DIR / "_shell_quality_recipes.py"

# The two names `checks/public_api_result_typed` accepts as railway-typed.
# Restated here rather than imported so this file pins the PROPERTY that check
# reads, independently of the check's own shape.
_RAILWAY_RETURN_NAMES = frozenset({"Result", "IOResult"})

_CONFORMING_JUSTFILE = "build:\n    @true\n"
# `just --dump` exits non-zero on this: `!!!` is not a recipe, an assignment or
# a setting, so the parser refuses the whole file.
_UNPARSEABLE_JUSTFILE = "build:\n    @true\n\n!!!\n"

_LEGACY_INTERPOLATED_WORKTREE_JUST = """# Legacy bootstrapped worktree pack fixture.

worktree-create branch base_ref="":
    ./dev-tooling/worktree-lib.sh create {{branch}} {{base_ref}}

worktree-hydrate:
    ./dev-tooling/worktree-lib.sh hydrate

worktree-land base_ref="":
    ./dev-tooling/worktree-lib.sh land {{base_ref}}

worktree-reap *args:
    ./dev-tooling/worktree-lib.sh reap {{args}}
"""


_BASH_ONLY_CONSTRUCT_RECIPES = """c1:
    ./x.sh "${@:2}"

c2:
    ./x.sh "[[ -n $v ]]"

c3:
    ./x.sh <<< "word"

c4:
    ./x.sh $'\\n'

c5:
    ./x.sh "${v//a/b}"

c6:
    ./x.sh "${v^^}"

c7:
    arr=(one two)

c8:
    function helper() { :; }
"""

_POSIX_CLEAN_PARAMETER_EXPANSIONS = """expansions:
    ./x.sh "${HOME:-/tmp}" "${PATH#*:}" "${f%/*}" "${p##*/}" "${v:=y}" "${z:?e}" "${q:+s}"
"""


def _git(*, cwd: Path, args: list[str]) -> None:
    _ = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        env={
            "HOME": str(cwd),
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "PATH": os.environ["PATH"],
        },
    )


def _write(*, root: Path, rel: str, body: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(body, encoding="utf-8")


def _terminal_return_name(*, rendered: str) -> str:
    """`IOResult[JustDump | None, RecipeDumpUnavailable]` → `IOResult`.

    Mirrors the reduction `public_api_result_typed` applies to a rendered
    return annotation before comparing it: drop the subscript, then drop any
    dotted qualifier.
    """
    return rendered.split("[", maxsplit=1)[0].rsplit(".", maxsplit=1)[-1]


def _return_annotations(*, path: Path) -> dict[str, str]:
    """Every top-level function in `path`, mapped to its rendered return."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name: ast.unparse(node.returns)
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.returns is not None
    }


def _stub_just_on_path(*, root: Path, monkeypatch: pytest.MonkeyPatch, body: str) -> None:
    """Put a `just` that prints `body` and exits 0 ahead of the real one."""
    stub_bin = root / "stub-bin"
    _write(root=stub_bin, rel="just", body=f"#!/usr/bin/env bash\nprintf '%s' {body!r}\n")
    stub = stub_bin / "just"
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{stub_bin}{os.pathsep}{os.environ['PATH']}")


def _run_check(
    *, cwd: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> tuple[int, str]:
    assert _CHECK_PATH.is_file(), "shell-quality check module should exist"
    _git(cwd=cwd, args=["init", "-q"])
    _git(cwd=cwd, args=["add", "-A"])
    monkeypatch.chdir(cwd)
    module = importlib.import_module("livespec_dev_tooling.checks.shell_quality")
    rc = module.main()
    captured = capsys.readouterr()
    return rc, captured.err


def test_shellcheck_warning_or_higher_fails_without_baseline(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write(
        root=tmp_path,
        rel="scripts/warning.sh",
        body="#!/usr/bin/env bash\nset -euo pipefail\nRUNNER_UID_HINT=1001\n",
    )

    rc, stderr = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc == 1, stderr
    assert '"check_id": "shell-quality"' in stderr
    assert '"code": "SC2034"' in stderr
    assert '"severity": "warning"' in stderr


def test_documented_no_errexit_deviation_passes(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write(
        root=tmp_path,
        rel="justfile",
        body="\n".join(
            [
                "# Deliberately omit errexit so every probe can run before summary.",
                "check-all:",
                "    #!/usr/bin/env bash",
                "    set -uo pipefail",
                "    failures=0",
                "    false || failures=$((failures + 1))",
                "    printf '%s\\n' \"${failures}\"",
                "",
            ]
        ),
    )
    _write(
        root=tmp_path,
        rel="scripts/clean.sh",
        body="#!/usr/bin/env bash\nset -euo pipefail\nprintf '%s\\n' ok\n",
    )

    rc, stderr = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc == 0, stderr


def test_multiline_errexit_recipe_fails(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write(
        root=tmp_path,
        rel="justfile",
        body="\n".join(
            [
                "build:",
                "    #!/usr/bin/env bash",
                "    set -euo pipefail",
                "    python -m build",
                "    python -m twine check dist/*",
                "",
            ]
        ),
    )
    _write(
        root=tmp_path,
        rel="scripts/clean.sh",
        body="#!/usr/bin/env bash\nset -euo pipefail\nprintf '%s\\n' ok\n",
    )

    rc, stderr = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc == 1, stderr
    assert '"reason": "nonconforming-just-recipe"' in stderr
    assert '"recipe": "build"' in stderr


def test_accidental_masked_coverage_omission_fails(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write(
        root=tmp_path,
        rel="justfile",
        body="\n".join(
            [
                "check-per-file-coverage:",
                "    #!/usr/bin/env bash",
                "    set -uo pipefail",
                "    pytest --cov",
                "    python -m coverage_gate",
                "",
            ]
        ),
    )
    _write(
        root=tmp_path,
        rel="scripts/clean.sh",
        body="#!/usr/bin/env bash\nset -euo pipefail\nprintf '%s\\n' ok\n",
    )

    rc, stderr = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc == 1, stderr
    assert '"reason": "missing-errexit-rationale"' in stderr
    assert '"recipe": "check-per-file-coverage"' in stderr


def test_incidental_hyphen_e_in_doc_does_not_buy_the_deviation_exemption(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An ordinary hyphenated word must not exempt an undocumented deviation.

    The documented-deviation exemption is what lets a recipe omit errexit
    deliberately. It must be earned by DOCUMENTING the rationale — never by a
    doc that merely happens to contain the two characters ``-e`` inside an
    unrelated hyphenated word. The doc below gives no errexit rationale at
    all; ``byte-for-entry`` is the only thing in it resembling ``-e``.
    """
    _write(
        root=tmp_path,
        rel="justfile",
        body="\n".join(
            [
                "# The script compares it byte-for-entry with check-targets.txt "
                "before dispatch.",
                "check:",
                "    #!/usr/bin/env bash",
                "    set -uo pipefail",
                "    echo one",
                "    echo two",
                "",
            ]
        ),
    )
    _write(
        root=tmp_path,
        rel="scripts/clean.sh",
        body="#!/usr/bin/env bash\nset -euo pipefail\nprintf '%s\\n' ok\n",
    )

    rc, stderr = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc == 1, stderr
    assert '"reason": "missing-errexit-rationale"' in stderr
    assert '"recipe": "check"' in stderr


def test_just_interpolation_in_recipe_body_fails(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write(
        root=tmp_path,
        rel="justfile",
        body="\n".join(
            [
                "run arg:",
                "    python tool.py {{arg}}",
                "",
            ]
        ),
    )
    _write(
        root=tmp_path,
        rel="scripts/clean.sh",
        body="#!/usr/bin/env bash\nset -euo pipefail\nprintf '%s\\n' ok\n",
    )

    rc, stderr = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc == 1, stderr
    assert '"reason": "just-interpolation"' in stderr
    assert '"recipe": "run"' in stderr


def test_parameterized_recipe_without_per_recipe_positional_arguments_fails(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write(
        root=tmp_path,
        rel="justfile",
        body="\n".join(
            [
                "set positional-arguments",
                "",
                "run *args:",
                '    scripts/run.sh "$@"',
                "",
            ]
        ),
    )
    _write(
        root=tmp_path,
        rel="scripts/run.sh",
        body="#!/usr/bin/env bash\nset -euo pipefail\nprintf '%s\\n' \"$@\"\n",
    )

    rc, stderr = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc == 1, stderr
    assert '"reason": "global-positional-arguments"' in stderr
    assert '"reason": "missing-per-recipe-positional-arguments"' in stderr
    assert '"recipe": "run"' in stderr


def test_thin_parameterized_recipe_with_per_recipe_positional_arguments_passes(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write(
        root=tmp_path,
        rel="justfile",
        body="\n".join(
            [
                "[positional-arguments]",
                "run *args:",
                '    scripts/run.sh "$@"',
                "",
            ]
        ),
    )
    _write(
        root=tmp_path,
        rel="scripts/run.sh",
        body="#!/usr/bin/env bash\nset -euo pipefail\nprintf '%s\\n' \"$@\"\n",
    )

    rc, stderr = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc == 0, stderr


def test_bootstrapped_legacy_worktree_pack_fragment_fails(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write(root=tmp_path, rel="justfile", body="import? 'dev-tooling/worktree.just'\n")
    _write(
        root=tmp_path,
        rel="dev-tooling/worktree.just",
        body=_LEGACY_INTERPOLATED_WORKTREE_JUST,
    )
    _write(
        root=tmp_path,
        rel="dev-tooling/worktree-lib.sh",
        body="#!/usr/bin/env bash\nset -euo pipefail\nprintf '%s\\n' \"$@\"\n",
    )

    rc, stderr = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc == 1, stderr
    for recipe in ("worktree-create", "worktree-land", "worktree-reap"):
        assert f'"recipe": "{recipe}"' in stderr
    assert stderr.count('"reason": "just-interpolation"') == 3
    assert stderr.count('"reason": "missing-per-recipe-positional-arguments"') == 3


def test_bootstrapped_canonical_worktree_pack_fragment_passes(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write(root=tmp_path, rel="justfile", body="import? 'dev-tooling/worktree.just'\n")
    _write(root=tmp_path, rel="dev-tooling/worktree.just", body=CANONICAL_WORKTREE_JUST_BODY)
    _write(
        root=tmp_path,
        rel="dev-tooling/worktree-lib.sh",
        body="#!/usr/bin/env bash\nset -euo pipefail\nprintf '%s\\n' \"$@\"\n",
    )
    _git(cwd=tmp_path, args=["init", "-q"])
    _git(cwd=tmp_path, args=["add", "-A"])

    module = importlib.import_module("livespec_dev_tooling.checks.shell_quality")
    assert hasattr(module, "findings_for_repo")
    assert module.findings_for_repo(repo_root=tmp_path) == []

    rc, stderr = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc == 0, stderr


def test_empty_shell_corpus_is_a_clean_pass(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A repo with zero tracked shell files passes; it does not crash.

    An empty corpus is the CORRECT state for a shell-free repo, not an error,
    so the honest outcome is a clean pass — neither a finding nor an exception.
    Before this was covered, `_shellcheck_findings` discriminated only the
    `ShellCheckUnavailable` failure member and fell through to `.unwrap()` on
    an already-failed `Result`, so the check raised `UnwrapFailedError` at a
    consumer that had done nothing wrong.

    The `ShellCorpusEmpty` arm is pinned DIRECTLY rather than inferred from the
    check's exit code: `run_shellcheck` returns that member before it ever
    looks for the binary, so asserting the member is what proves this test
    exercises the empty-corpus return and not the missing-binary one. Asserting
    only "no exception" would also pass against a broad `except` swallow, which
    is the false-negative shape this check must never adopt.
    """
    _write(root=tmp_path, rel="README.md", body="no tracked shell files\n")
    _git(cwd=tmp_path, args=["init", "-q"])
    _git(cwd=tmp_path, args=["add", "-A"])

    assert isinstance(run_shellcheck(repo_root=tmp_path).failure(), ShellCorpusEmpty)

    module = importlib.import_module("livespec_dev_tooling.checks.shell_quality")
    assert module.findings_for_repo(repo_root=tmp_path) == []

    rc, stderr = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc == 0, stderr


def test_bash_array_slice_in_default_sh_recipe_body_fails(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The `livespec-f3tf` defect, reproduced as a fixture.

    `reap-stale-worktrees` passed `"${@:2}"` — a Bash array slice — to a
    logic-free pass-through recipe. The body is perfectly CONFORMING by every
    shape rule: one command, no shebang, no forbidden metacharacter, and the
    per-recipe `positional-arguments` attribute is present. Under `just`'s
    default `sh` it is nevertheless a `Bad substitution` abort on every single
    invocation, so the recipe never ran for the whole of its life while the
    gate that inspected it stayed green.
    """
    _write(
        root=tmp_path,
        rel="justfile",
        body="\n".join(
            [
                "[positional-arguments]",
                "reap-stale-worktrees *args:",
                '    ./dev-tooling/worktree-lib.sh reap "${@:2}"',
                "",
            ]
        ),
    )
    _write(
        root=tmp_path,
        rel="dev-tooling/worktree-lib.sh",
        body="#!/usr/bin/env bash\nset -euo pipefail\nprintf '%s\\n' \"$@\"\n",
    )

    rc, stderr = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc == 1, stderr
    assert '"reason": "bash-only-syntax-under-default-sh"' in stderr
    assert '"recipe": "reap-stale-worktrees"' in stderr
    assert '"construct": "array-slice"' in stderr


def test_every_bash_only_construct_is_reported_under_default_sh(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write(root=tmp_path, rel="justfile", body=_BASH_ONLY_CONSTRUCT_RECIPES)
    _write(
        root=tmp_path,
        rel="scripts/clean.sh",
        body="#!/usr/bin/env bash\nset -euo pipefail\nprintf '%s\\n' ok\n",
    )

    rc, stderr = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc == 1, stderr
    for construct in (
        "array-slice",
        "double-bracket-test",
        "here-string",
        "ansi-c-quoting",
        "pattern-substitution",
        "case-conversion",
        "array-assignment",
        "function-keyword",
    ):
        assert f'"construct": "{construct}"' in stderr


def test_posix_parameter_expansions_do_not_trip_the_bash_only_lexicon(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The near-neighbours that make this a discrimination rather than a grep.

    `${v:-d}`, `${v:=d}`, `${v:?e}` and `${v:+s}` all put a `:` where the Bash
    slice puts its offset, and `${p#*:}`, `${f%/*}` and `${p##*/}` all put a
    `/` or a `:` inside the braces where pattern substitution puts its
    separator. Every one of them is POSIX and runs correctly under dash, so a
    substring test for `:` or `/` inside `${...}` would condemn a clean body.
    """
    _write(root=tmp_path, rel="justfile", body=_POSIX_CLEAN_PARAMETER_EXPANSIONS)
    _write(
        root=tmp_path,
        rel="scripts/clean.sh",
        body="#!/usr/bin/env bash\nset -euo pipefail\nprintf '%s\\n' ok\n",
    )

    rc, stderr = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc == 0, stderr


def test_shebang_recipe_may_use_bash_only_syntax(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A shebang body names its own interpreter, so the lexicon does not apply."""
    _write(
        root=tmp_path,
        rel="justfile",
        body="\n".join(
            [
                "# Deliberately omit errexit so every probe can run before summary.",
                "probe-all:",
                "    #!/usr/bin/env bash",
                "    set -uo pipefail",
                "    names=(one two)",
                '    [[ -n "${names[@]:1}" ]] && printf \'%s\\n\' "${names[0]^^}"',
                "",
            ]
        ),
    )
    _write(
        root=tmp_path,
        rel="scripts/clean.sh",
        body="#!/usr/bin/env bash\nset -euo pipefail\nprintf '%s\\n' ok\n",
    )

    rc, stderr = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc == 0, stderr


def test_declared_bash_compatible_set_shell_exempts_the_whole_justfile(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`set shell` is file-scoped, so a Bash declaration retires the lexicon."""
    _write(
        root=tmp_path,
        rel="justfile",
        body="\n".join(
            [
                'set shell := ["bash", "-cu"]',
                "",
                "slice:",
                '    ./scripts/run.sh "${@:2}"',
                "",
            ]
        ),
    )
    _write(
        root=tmp_path,
        rel="scripts/run.sh",
        body="#!/usr/bin/env bash\nset -euo pipefail\nprintf '%s\\n' \"$@\"\n",
    )

    rc, stderr = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc == 0, stderr


def test_declared_posix_set_shell_keeps_the_lexicon_armed(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An unrecognised or POSIX `set shell` is not an exemption.

    The exemption is granted only for interpreters KNOWN to understand the
    lexicon. Treating an unrecognised declaration as Bash-compatible would
    trade a visible false finding for the silent recipe death this rule exists
    to prevent, so the default runs the other way.
    """
    _write(
        root=tmp_path,
        rel="justfile",
        body="\n".join(
            [
                'set shell := ["/bin/dash", "-c"]',
                "",
                "slice:",
                '    ./scripts/run.sh "${@:2}"',
                "",
            ]
        ),
    )
    _write(
        root=tmp_path,
        rel="scripts/run.sh",
        body="#!/usr/bin/env bash\nset -euo pipefail\nprintf '%s\\n' \"$@\"\n",
    )

    rc, stderr = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc == 1, stderr
    assert '"reason": "bash-only-syntax-under-default-sh"' in stderr
    assert '"construct": "array-slice"' in stderr


def test_this_repos_own_justfile_carries_no_bash_only_syntax() -> None:
    """The measured containment claim, pinned as an assertion.

    The work-item's sweep found zero findings across all eleven fleet justfiles,
    so arming this rule reddens nothing. Only this repo's justfile is reachable
    from inside a test, and it is the one that gates every commit here.
    """
    module = importlib.import_module("livespec_dev_tooling.checks._shell_quality_recipes")
    dumped = module.recipe_findings(repo_root=_REPO_ROOT)

    # The claim is about what the rule FOUND, so the dump it rests on has to
    # have been obtained: an unread justfile would satisfy an emptiness
    # assertion for the one reason this test is not allowed to accept.
    assert is_successful(dumped), unsafe_perform_io(dumped.failure())
    findings = unsafe_perform_io(dumped.unwrap())
    assert [f for f in findings if f.reason == "bash-only-syntax-under-default-sh"] == []


def test_the_dump_acquisition_lives_in_its_own_module() -> None:
    """Obtaining the dump is its own concern, not a section of the policy."""
    assert _DUMP_MODULE_PATH.is_file(), (
        "the `just --dump` acquisition half must live at "
        f"{_DUMP_MODULE_PATH.name}, beside the policy half it was split from"
    )
    module = importlib.import_module("livespec_dev_tooling.checks._shell_quality_dump")
    policy = importlib.import_module("livespec_dev_tooling.checks._shell_quality_recipes")

    assert "just_dump" in module.__all__
    assert "RecipeDumpUnavailable" in module.__all__
    assert not hasattr(
        policy, "_just_dump"
    ), "the policy half must no longer carry a dump reader of its own"


def test_both_public_readers_announce_a_failure_track_in_their_return() -> None:
    """`just_dump` and `recipe_findings` are railway-typed, read as the check reads it."""
    assert (
        _DUMP_MODULE_PATH.is_file()
    ), f"{_DUMP_MODULE_PATH.name} must exist before its annotations can be read"
    dump_returns = _return_annotations(path=_DUMP_MODULE_PATH)
    policy_returns = _return_annotations(path=_POLICY_MODULE_PATH)

    assert _terminal_return_name(rendered=dump_returns["just_dump"]) in _RAILWAY_RETURN_NAMES
    assert (
        _terminal_return_name(rendered=policy_returns["recipe_findings"]) in _RAILWAY_RETURN_NAMES
    )


def test_a_repo_with_no_justfile_answers_rather_than_failing(*, tmp_path: Path) -> None:
    """Absence is the ANSWER: no justfile means no recipes, not an unread dump.

    The half of the distinction that is easy to lose. Reading absence as a
    failure would be the smaller diff and it would convict every justfile-free
    consumer of a dump nobody could obtain.
    """
    module = importlib.import_module("livespec_dev_tooling.checks._shell_quality_dump")

    dumped = module.just_dump(repo_root=tmp_path)

    assert is_successful(dumped)
    assert unsafe_perform_io(dumped.unwrap()) is None


def test_a_conforming_justfile_yields_the_parsed_payload(*, tmp_path: Path) -> None:
    module = importlib.import_module("livespec_dev_tooling.checks._shell_quality_dump")
    _write(root=tmp_path, rel="justfile", body=_CONFORMING_JUSTFILE)

    dumped = module.just_dump(repo_root=tmp_path)

    assert is_successful(dumped)
    assert "build" in unsafe_perform_io(dumped.unwrap())["recipes"]


def test_just_absent_from_path_is_the_failure_track(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No `just` on PATH used to `cast` a `None` binary into `subprocess.run`."""
    module = importlib.import_module("livespec_dev_tooling.checks._shell_quality_dump")
    _write(root=tmp_path, rel="justfile", body=_CONFORMING_JUSTFILE)
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", str(empty_bin))

    dumped = module.just_dump(repo_root=tmp_path)

    assert not is_successful(dumped)
    failure = unsafe_perform_io(dumped.failure())
    assert failure.reason == "just-unavailable"
    assert "mise install just" in failure.remedy


def test_a_justfile_the_parser_rejects_is_the_failure_track(*, tmp_path: Path) -> None:
    """A non-zero dump left `json.loads("")` raising out of the check."""
    module = importlib.import_module("livespec_dev_tooling.checks._shell_quality_dump")
    _write(root=tmp_path, rel="justfile", body=_UNPARSEABLE_JUSTFILE)

    dumped = module.just_dump(repo_root=tmp_path)

    assert not is_successful(dumped)
    failure = unsafe_perform_io(dumped.failure())
    assert failure.reason == "just-dump-failed"
    assert str(tmp_path) in failure.remedy


def test_a_dump_that_exits_zero_without_a_json_object_is_the_failure_track(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Output this module cannot interpret is not an empty justfile.

    The silent one: a payload that is not a JSON object used to be degraded to
    `{}`, which the policy then reports as a repo whose every recipe conforms.
    """
    module = importlib.import_module("livespec_dev_tooling.checks._shell_quality_dump")
    _write(root=tmp_path, rel="justfile", body=_CONFORMING_JUSTFILE)
    _stub_just_on_path(root=tmp_path, monkeypatch=monkeypatch, body="not json at all")

    dumped = module.just_dump(repo_root=tmp_path)

    assert not is_successful(dumped)
    failure = unsafe_perform_io(dumped.failure())
    assert failure.reason == "just-dump-unparseable"
    assert "inspect the output" in failure.remedy


def test_an_unobtained_recipe_dump_is_reported_rather_than_read_as_clean(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A justfile the check never read must not reach the verdict as a clean one.

    The recipe half's counterpart to `shellcheck-unavailable`: the check's
    verdict is a finding LIST, so the dump's failure track is rendered as a
    finding here rather than propagating. Before the railway this repo's
    recipe policy answered a rejected justfile by raising a `JSONDecodeError`
    out of the check — and a payload it could not interpret by reporting zero
    recipe findings, which is a pass over recipes nobody read.
    """
    _write(root=tmp_path, rel="justfile", body="build:\n    @true\n\n!!!\n")
    _write(
        root=tmp_path,
        rel="scripts/run.sh",
        body="#!/usr/bin/env bash\nset -euo pipefail\nprintf '%s\\n' ok\n",
    )

    rc, stderr = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc == 1, stderr
    assert '"reason": "just-dump-failed"' in stderr
    assert '"binary_name": "just"' in stderr
    assert "re-run check-shell-quality" in stderr


def test_missing_shellcheck_binary_hard_fails_with_actionable_remedy(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write(
        root=tmp_path,
        rel="scripts/clean.sh",
        body="#!/usr/bin/env bash\nset -euo pipefail\nprintf '%s\\n' ok\n",
    )
    module = importlib.import_module("livespec_dev_tooling.checks.shell_quality")
    unavailable = ShellCheckUnavailable(
        binary_name="shellcheck",
        required_version="0.11.0",
        remedy=(
            "install ShellCheck 0.11.0 and expose it on PATH, for example with "
            "`mise install shellcheck@0.11.0` from the consumer repo"
        ),
    )
    monkeypatch.setattr(
        module,
        "run_shellcheck",
        lambda *, repo_root: Failure(unavailable) if repo_root else Failure(unavailable),
    )

    try:
        rc, stderr = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    except UnwrapFailedError as exc:  # pragma: no cover
        pytest.fail(f"expected a shell-quality finding, got unwrap failure: {exc}")

    assert rc == 1, stderr
    assert '"reason": "shellcheck-unavailable"' in stderr
    assert '"binary_name": "shellcheck"' in stderr
    assert '"required_version": "0.11.0"' in stderr
    assert "`mise install shellcheck@0.11.0` from the consumer repo" in stderr

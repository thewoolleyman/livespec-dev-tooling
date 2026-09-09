"""Tests for the canonical shell-quality policy check."""

from __future__ import annotations

import importlib
import os
import subprocess
from pathlib import Path

import pytest
from returns.primitives.exceptions import UnwrapFailedError
from returns.result import Failure

from livespec_dev_tooling.install_worktree_pack import CANONICAL_WORKTREE_JUST_BODY
from livespec_dev_tooling.shellcheck import (
    ShellCheckUnavailable,
    ShellCorpusEmpty,
    run_shellcheck,
)

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK_PATH = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "shell_quality.py"

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
    findings = module.recipe_findings(repo_root=_REPO_ROOT)

    assert [f for f in findings if f.reason == "bash-only-syntax-under-default-sh"] == []


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

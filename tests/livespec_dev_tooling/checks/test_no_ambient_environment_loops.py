"""Outside-in tests for `livespec_dev_tooling/checks/no_ambient_environment_loops.py`.

Work item livespec-dev-tooling-dpkz32. A `for` / `async for` statement whose
iterable reads `os.environ` runs its body only on a host carrying a matching
variable, so a test file's coverage depends on the host. The check fails every
such loop under the consumer's `tests_tree_prefix` — written directly, through
an import alias, or through a name bound in the same scope from `os.environ`,
`os.environ.copy()` or `dict(os.environ)` — and names a single-expression
rewrite. It follows no other indirection and honours no pragma.

Every case drives `main()` in-process over a fixture consumer tree
(`monkeypatch.chdir` + `capsys`), and reads the structured findings off stderr.
"""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
from types import ModuleType

import pytest

from tests.livespec_dev_tooling.checks.config_parse_rendering import (
    assert_main_renders_the_parse_failure,
)

__all__: list[str] = []

_MODULE = "livespec_dev_tooling.checks.no_ambient_environment_loops"
_CHECK_ID = "no_ambient_environment_loops"

_SCENARIO_BODY = (
    "import os\n"
    "\n"
    "\n"
    "def test_scrub(monkeypatch):\n"
    '    for name in [n for n in os.environ if n.startswith("GIT_")]:\n'
    "        monkeypatch.delenv(name)  # pragma: no cover\n"
)

_REWRITTEN_BODY = (
    "import os\n"
    "\n"
    "\n"
    "def test_scrub(monkeypatch):\n"
    '    _ = [monkeypatch.delenv(n) for n in os.environ if n.startswith("GIT_")]\n'
    "    for value in [1, 2]:\n"
    "        assert value\n"
)

_ASYNC_BODY = (
    "import os\n"
    "\n"
    "\n"
    "async def test_async(agen):\n"
    "    async for key in agen(os.environ):\n"
    "        await key\n"
)

_ALIAS_BODY = (
    "from __future__ import annotations\n"
    "\n"
    "import os as o\n"
    "from os import environ\n"
    "from os import environ as ambient\n"
    "\n"
    "\n"
    "def test_module_alias():\n"
    "    for key in o.environ:  # module-alias\n"
    "        assert key\n"
    "\n"
    "\n"
    "def test_from_import():\n"
    "    for key in sorted(environ):  # from-import\n"
    "        assert key\n"
    "\n"
    "\n"
    "def test_from_import_as():\n"
    "    for key, value in ambient.items():  # from-import-as\n"
    "        assert key, value\n"
)

_BINDING_BODY = (
    "import os\n"
    "\n"
    "MODULE_ENV = dict(os.environ)\n"
    "for key in MODULE_ENV:  # module-scope\n"
    "    print(key)\n"
    "\n"
    "\n"
    "def test_bare_binding():\n"
    "    env = os.environ\n"
    "    for key in env:  # bound-bare\n"
    "        assert key\n"
    "\n"
    "\n"
    "def test_copy_binding():\n"
    "    env = os.environ.copy()\n"
    "    for key in list(env):  # bound-copy\n"
    "        assert key\n"
    "\n"
    "\n"
    "def test_dict_binding():\n"
    "    env: dict[str, str] = dict(os.environ)\n"
    "    for key in env.items():  # bound-dict\n"
    "        assert key\n"
)

_MODULE_BINDING_BODY = (
    "import os\n"
    "\n"
    "ENV = os.environ\n"
    "ENV_COPY = os.environ.copy()\n"
    "ENV_DICT = dict(os.environ)\n"
    "\n"
    "\n"
    "def helper_bare():\n"
    "    for key in ENV:  # module-bare\n"
    "        assert key\n"
    "\n"
    "\n"
    "def helper_copy():\n"
    "    for key in sorted(ENV_COPY):  # module-copy\n"
    "        assert key\n"
    "\n"
    "\n"
    "def helper_dict():\n"
    "    for key, value in ENV_DICT.items():  # module-dict\n"
    "        assert key, value\n"
    "\n"
    "\n"
    "def sibling_binds():\n"
    "    local_env = dict(os.environ)\n"
    "    return local_env\n"
    "\n"
    "\n"
    "def sibling_reads(local_env):\n"
    "    for key in local_env:  # sibling\n"
    "        assert key\n"
)

_OUT_OF_SCOPE_BODY = (
    "import os\n"
    "\n"
    "\n"
    "def make_env():\n"
    "    env = dict(os.environ)\n"
    "    return env\n"
    "\n"
    "\n"
    "def test_other_scope(env):\n"
    "    for key in env:\n"
    "        assert key\n"
    "\n"
    "\n"
    "def test_unfollowed_bindings():\n"
    "    chained = make_env()\n"
    '    value = os.environ.get("HOME")\n'
    '    widened = dict(os.environ, EXTRA="1")\n'
    "    copied = os.environ.copy\n"
    "    counted: int\n"
    "    total = len(os.environ)\n"
    "    total += 1\n"
    "    first = second = chained\n"
    "    for key in chained:\n"
    "        assert key, (value, widened, copied, total, first, second)\n"
    "    handler = lambda: [k for k in os.environ]\n"
    "    assert handler\n"
)


def _write(*, root: Path, files: dict[str, str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _ = (root / "pyproject.toml").write_text(
        '[tool.livespec_dev_tooling]\ntests_tree_prefix = "tests/"\n', encoding="utf-8"
    )
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(body, encoding="utf-8")


def _module() -> ModuleType:
    return importlib.import_module(_MODULE)


def _run(
    *,
    root: Path,
    files: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, list[dict[str, object]]]:
    _write(root=root, files=files)
    monkeypatch.chdir(root)
    rc = _module().main()
    events = [json.loads(line) for line in capsys.readouterr().err.splitlines() if line.strip()]
    findings = [event for event in events if event.get("status") == "fail"]
    return rc, findings


def _line_of(*, body: str, needle: str) -> int:
    return next(number for number, text in enumerate(body.splitlines(), start=1) if needle in text)


def _located(*, findings: list[dict[str, object]]) -> list[tuple[object, object]]:
    return sorted((finding["file"], finding["line"]) for finding in findings)


@pytest.mark.parametrize("host_git_variables", [{"GIT_AMBIENT_PROBE": "1"}, {}])
def test_the_scenario_loop_fails_on_every_host_naming_file_line_and_rewrite(
    *,
    host_git_variables: dict[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The loop fails with or without a `GIT_` variable, and the pragma changes nothing."""
    _ = [monkeypatch.delenv(n) for n in list(os.environ) if n.startswith("GIT_")]
    _ = [monkeypatch.setenv(n, v) for n, v in host_git_variables.items()]

    rc, findings = _run(
        root=tmp_path,
        files={"tests/test_scrub.py": _SCENARIO_BODY},
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    assert rc == 4
    assert len(findings) == 1
    finding = findings[0]
    assert finding["check_id"] == _CHECK_ID
    assert finding["failure_mode"] == "ambient_environment_loop"
    assert finding["file"] == "tests/test_scrub.py"
    assert finding["line"] == _line_of(body=_SCENARIO_BODY, needle="for name in")
    assert finding["rewrite"] == (
        "_ = [monkeypatch.delenv(name) for name in [n for n in os.environ if n.startswith('GIT_')]]"
    )


@pytest.mark.parametrize("host_git_variables", [{"GIT_AMBIENT_PROBE": "1"}, {}])
def test_the_single_expression_rewrite_passes_on_every_host(
    *,
    host_git_variables: dict[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A comprehension over os.environ, and a loop over anything else, pass with exit 0."""
    _ = [monkeypatch.delenv(n) for n in list(os.environ) if n.startswith("GIT_")]
    _ = [monkeypatch.setenv(n, v) for n, v in host_git_variables.items()]

    rc, findings = _run(
        root=tmp_path,
        files={"tests/test_scrub.py": _REWRITTEN_BODY},
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    assert (rc, findings) == (0, [])


def test_an_async_for_over_os_environ_fails_with_an_async_rewrite(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, findings = _run(
        root=tmp_path,
        files={"tests/test_async.py": _ASYNC_BODY},
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    assert rc == 4
    assert _located(findings=findings) == [
        ("tests/test_async.py", _line_of(body=_ASYNC_BODY, needle="async for"))
    ]
    assert findings[0]["rewrite"] == "_ = [await key async for key in agen(os.environ)]"


def test_both_import_alias_forms_are_followed(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, findings = _run(
        root=tmp_path,
        files={"tests/sub/test_alias.py": _ALIAS_BODY},
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    assert rc == 4
    assert _located(findings=findings) == [
        ("tests/sub/test_alias.py", _line_of(body=_ALIAS_BODY, needle=marker))
        for marker in ("# module-alias", "# from-import", "# from-import-as")
    ]
    assert findings[0]["rewrite"] == "_ = [<expression> for key in o.environ]"


def test_each_same_scope_binding_form_is_followed(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, findings = _run(
        root=tmp_path,
        files={"tests/test_binding.py": _BINDING_BODY},
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    assert rc == 4
    assert _located(findings=findings) == [
        ("tests/test_binding.py", _line_of(body=_BINDING_BODY, needle=marker))
        for marker in ("# module-scope", "# bound-bare", "# bound-copy", "# bound-dict")
    ]
    assert findings[0]["rewrite"] == "_ = [print(key) for key in MODULE_ENV]"


def test_a_module_level_binding_is_followed_into_a_function_but_a_sibling_s_is_not(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A function loop over a module-level name bound from any of the three forms fails.

    A name bound in a SIBLING function's scope is not followed: the loop in
    `sibling_reads` iterates its own parameter.
    """
    rc, findings = _run(
        root=tmp_path,
        files={"tests/test_module_binding.py": _MODULE_BINDING_BODY},
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    assert rc == 4
    assert _located(findings=findings) == [
        ("tests/test_module_binding.py", _line_of(body=_MODULE_BINDING_BODY, needle=marker))
        for marker in ("# module-bare", "# module-copy", "# module-dict")
    ]


def test_indirection_outside_the_named_forms_is_not_followed(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A name bound in ANOTHER scope, a call result, or a chained name is out of scope."""
    rc, findings = _run(
        root=tmp_path,
        files={"tests/test_out_of_scope.py": _OUT_OF_SCOPE_BODY},
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    assert (rc, findings) == (0, [])


def test_findings_span_files_and_a_missing_tests_tree_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every offending file is reported; a consumer with no tests tree passes."""
    rc, findings = _run(
        root=tmp_path / "with_tests",
        files={
            "tests/test_scrub.py": _SCENARIO_BODY,
            "tests/test_async.py": _ASYNC_BODY,
            "tests/test_clean.py": _REWRITTEN_BODY,
            "src/test_outside.py": _SCENARIO_BODY,
        },
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
    empty_rc, empty_findings = _run(
        root=tmp_path / "without_tests", files={}, monkeypatch=monkeypatch, capsys=capsys
    )

    assert rc == 4
    assert [finding["file"] for finding in findings] == [
        "tests/test_async.py",
        "tests/test_scrub.py",
    ]
    assert (empty_rc, empty_findings) == (0, [])


def test_main_renders_the_consumer_config_parse_failure(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert_main_renders_the_parse_failure(
        module_slug=_CHECK_ID,
        check_id=_CHECK_ID,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

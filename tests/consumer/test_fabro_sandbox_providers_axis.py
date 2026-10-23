"""Consumer-tier: the `fabro_server` role's `sandbox_providers` axis.

The `## Fabro factory host provisioning` section of
`SPECIFICATION/non-functional-requirements.md` ("One instance per mapping") requires that
adding an optional axis never changes an instance that does not use it. This module holds
the `sandbox_providers` axis to that rule and to its own refusals: it is optional with an
empty-mapping default, the settings template renders it only inside one loop over that
mapping (so an empty mapping renders the pre-axis bytes), malformed provider declarations
and environments naming an undeclared provider are refused before the role's first write,
and an environment's optional `provider` reaches the catalog body and the match decision.

Text-sliced rather than rendered or YAML-parsed, for the reason the sibling catalog module
gives: neither Jinja nor a YAML library is importable in this suite. Each arm therefore
asserts the SHAPE of the role's own expressions, read out of the committed files.
"""

from __future__ import annotations

import re
from itertools import pairwise
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROLE = _REPO_ROOT / "ansible" / "roles" / "fabro_server"
_TASKS = _ROLE / "tasks" / "main.yml"
_ENVIRONMENT_TASKS = _ROLE / "tasks" / "environment.yml"
_SETTINGS = _ROLE / "templates" / "settings.toml.j2"
_ROLE_DOC = _ROLE / "HOST_VARS.md"

_AXIS = "sandbox_providers"
_FACT = "fabro_server_sandbox_providers"
_RESOLVE_TASK = "Resolve this instance's axes"
_MAPPING_REFUSAL = "Refuse an instance mapping that does not spell every axis"
_PROVIDER_REFUSAL = "Refuse a sandbox provider declaration Fabro would refuse or could not verify"
_ENV_PROVIDER_REFUSAL = "Refuse an environment whose provider this instance does not declare"
_FIRST_WRITE = "Create the shared libexec directory"
_LOOP_OPEN = "{% for kind, provider in fabro_server_sandbox_providers | dictsort %}"


def _tasks_of(*, source: Path) -> list[tuple[str, str]]:
    """Every top-level task of one role file, as `(name, body)` in file order."""
    assert source.is_file(), f"the role MUST carry {source.name}"
    text = source.read_text(encoding="utf-8")
    openings = [match.start() for match in re.finditer(r"^- name: ", text, re.MULTILINE)]
    assert openings, f"{source.name} must carry column-zero `- name:` tasks"
    bounds = [*openings, len(text)]
    tasks: list[tuple[str, str]] = []
    for start, end in pairwise(bounds):
        body = text[start:end]
        tasks.append((body.splitlines()[0].removeprefix("- name: ").strip(), body))
    return tasks


def _named(*, name: str, source: Path) -> str:
    matching = [body for task_name, body in _tasks_of(source=source) if task_name == name]
    assert len(matching) == 1, f"{source.name} must carry exactly one task named {name!r}"
    return matching[0]


def _task_index(*, name: str, source: Path) -> int:
    names = [task_name for task_name, _ in _tasks_of(source=source)]
    assert name in names, f"{source.name} must still carry the task {name!r}"
    return names.index(name)


def test_the_axis_is_optional_and_defaults_to_the_empty_mapping() -> None:
    resolve = _named(name=_RESOLVE_TASK, source=_TASKS)
    expected = f'{_FACT}: "{{{{ fabro_server_instance.{_AXIS} | default({{}}) }}}}"'
    assert expected in resolve, (
        f"the role MUST resolve {_FACT} from the instance mapping with an empty-mapping "
        f"default; an empty mapping is the only default that leaves every instance "
        f"predating the axis configuring no plugin"
    )
    refusal = _named(name=_MAPPING_REFUSAL, source=_TASKS)
    assert not re.search(
        rf"^\s+- {_AXIS}$", refusal, re.MULTILINE
    ), f"{_AXIS} MUST NOT join the keys every instance mapping must spell"


def test_an_empty_mapping_renders_settings_exactly_as_before_the_axis() -> None:
    text = _SETTINGS.read_text(encoding="utf-8")
    assert text.count(_LOOP_OPEN) == 1, "the provider tables MUST come from ONE loop"
    before, loop = text.split(_LOOP_OPEN)
    assert before.endswith("\n"), "the loop MUST open on its own line"
    assert (
        "fabro_server_sandbox_providers" not in before
    ), "nothing outside the loop may read the axis, or an empty mapping changes the render"
    assert loop.rstrip("\n").endswith("{% endfor %}"), (
        "the loop MUST be the template's last block, so with Ansible's trim_blocks an "
        "empty mapping emits no byte after the pre-axis body"
    )
    assert (
        loop.count("{% for ") == 0 and loop.count("{% endfor %}") == 1
    ), "the provider block must be a single, unnested loop"
    for line in (
        "[server.sandbox.providers.{{ kind }}]",
        "enabled = true",
        'path = "{{ provider.path }}"',
        'sha256 = "{{ provider.sha256 }}"',
    ):
        assert line in loop, f"each declared provider MUST render {line!r}"
    for optional in ("args", "inherit_env", "process_spec"):
        assert (
            f"{{% if provider.{optional} | default(" in loop
        ), f"{optional} is optional and MUST render only when declared"
    assert "host_address" not in loop, (
        "host_address MUST NOT render: a registered provider's sandboxes have no route "
        "back to the host, and Fabro's provider table rejects the key as unknown"
    )


def test_a_process_spec_renders_as_a_sandbox_spec_inline_table() -> None:
    loop = _SETTINGS.read_text(encoding="utf-8").split(_LOOP_OPEN)[1]
    lines = [line for line in loop.splitlines() if line.startswith("process_spec = ")]
    assert len(lines) == 1, "the provider block MUST render process_spec on exactly one line"
    rendered = (
        lines[0]
        .replace("{{ provider.process_spec.image }}", "ghcr.io/acme/runner:1")
        .replace("{{ provider.process_spec.cpu_cores | int }}", "4")
        .replace("{{ provider.process_spec.memory_mb | int }}", "7629")
    )
    assert rendered == (
        'process_spec = { source = { image = { reference = "ghcr.io/acme/runner:1" } }, '
        "resources = { cpu_cores = 4, memory_mb = 7629 } }"
    ), (
        "process_spec MUST render sandbox-driver's SandboxSpec shape as one TOML inline "
        f"table, source.image.reference plus resources, from exactly three keys: {rendered}"
    )


def test_malformed_provider_declarations_are_refused_before_the_first_write() -> None:
    refusal = _named(name=_PROVIDER_REFUSAL, source=_TASKS)
    for condition in (
        "item.key not in ['local', 'docker', 'daytona']",
        "item.value.path | default('') is match('^/')",
        "item.value.sha256 | default('') is match('^[0-9a-f]{64}$')",
        "item.value.host_address is not defined",
        "item.value.process_spec.image | default('') | length > 0",
    ):
        assert condition in refusal, f"the provider refusal MUST hold {condition!r}"
    assert (
        f'loop: "{{{{ {_FACT} | dict2items }}}}"' in refusal
    ), "the refusal MUST judge every declared provider"
    assert "notify" not in refusal, "a refusal MUST notify nothing"
    first_write = _task_index(name=_FIRST_WRITE, source=_TASKS)
    for name in (_PROVIDER_REFUSAL, _ENV_PROVIDER_REFUSAL):
        assert (
            _task_index(name=name, source=_TASKS) < first_write
        ), f"{name!r} MUST run before the role's first write to the host"


def test_an_environment_may_name_only_docker_or_a_declared_provider() -> None:
    refusal = _named(name=_ENV_PROVIDER_REFUSAL, source=_TASKS)
    assert (
        f"(item.provider | default('docker')) in (['docker'] + ({_FACT}.keys() | list))" in refusal
    ), "an environment's provider MUST default to docker and otherwise be a declared kind"
    assert 'loop: "{{ fabro_server_environments }}"' in refusal


def test_a_declared_provider_reaches_the_catalog_body_and_the_match_decision() -> None:
    text = _ENVIRONMENT_TASKS.read_text(encoding="utf-8")
    assert (
        "'provider': fabro_server_environment.provider | default(fabro_server_environment_base.provider)"
        in text
    ), "the written settings MUST carry the declared provider, else the base entry's"
    assert re.search(
        r"\(fabro_server_environment_current\.provider \| default\(''\)\)\s+==\s+"
        r"\(fabro_server_environment\.provider \| default\(",
        text,
    ), "the match decision MUST compare the provider, or a provider change never converges"
    assert (
        "in ['docker', fabro_server_environment.provider | default('docker')]" in text
    ), "the base-entry refusal MUST accept a base already on the declared provider"


def test_the_role_document_names_the_axis_and_its_plugin_environment() -> None:
    doc = _ROLE_DOC.read_text(encoding="utf-8")
    assert f"`{_AXIS}`" in doc and "`{}`" in doc
    assert "## Sandbox-driver plugin providers" in doc
    assert (
        "inherit_env" in doc and "HOME" in doc
    ), "the document MUST say the plugin's cleared environment needs HOME passed through"

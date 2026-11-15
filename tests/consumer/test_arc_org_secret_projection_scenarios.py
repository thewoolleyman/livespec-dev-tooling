"""Consumer-tier: the ARC secret reinjection's ORGANIZATION projection, from the shipped bytes.

The two `SPECIFICATION/scenarios.md` scenarios of `## Runner-pool node rebuild
recipe`'s paragraph "ARC GitHub App credentials, one Secret per account."
(livespec-dev-tooling-h5r75q):

- the projection writes the `livespec-ai-arc` credential into
  `arc-runners/arc-github-app-installation-livespec-ai`, leaves
  `arc-github-app-installation` byte-identical, and prints no value;
- a missing or empty value makes it exit non-zero, name each missing variable,
  print no value and leave the organization Secret unchanged.

WHY THE INJECTOR IS RUN FOR REAL, with a stand-in `kubectl` on its PATH. Each
claim is about what the shipped script DOES with its environment: which object
it writes, what reaches kubectl's argv, and whether it calls kubectl at all on
a refusal. Reading the script cannot establish that. The stand-in is a bash
script (no Python child, so nothing self-instruments under coverage) that keeps
each Secret as a file in a state directory, records every argv, and answers the
injector's create, replace and get calls the way kubectl does for them. No
cluster is reached and no real credential exists: the three values are
fixtures. Running the launcher, the unit and the RBAC against the real k3s
cluster is the host-captured half of the work item.
"""

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-mzbt35
from __future__ import annotations

import base64
import itertools
import re
import subprocess
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REINJECTION = _REPO_ROOT / "ci-runner" / "k3s" / "secret-reinjection"
_INJECTOR = _REINJECTION / "inject-github-app-secret-livespec-ai.sh"
_RBAC = _REINJECTION / "arc-org-projector-rbac.yaml"
_ROLE = _REPO_ROOT / "ansible" / "roles" / "secret_reinjection"

_NAMESPACE = "arc-runners"
_ORG_SECRET = "arc-github-app-installation-livespec-ai"
_PERSONAL_SECRET = "arc-github-app-installation"

# Fixture values, shaped like the real ones (two integers and a PEM) and unique
# enough that finding one in an argv or in the output can only mean a leak.
_VALUES = {
    "LIVESPEC_AI_ARC_APP_ID": "90817263",
    "LIVESPEC_AI_ARC_INSTALLATION_ID": "45362718",
    "LIVESPEC_AI_ARC_PRIVATE_KEY": (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "fixtureKeyLineOneQWxhZGRpbiBvcGVuIHNlc2FtZQ\n"
        "fixtureKeyLineTwoZm9yIHRoZSB0ZXN0IG9ubHk\n"
        "-----END RSA PRIVATE KEY-----"
    ),
}
_KEY_OF = {
    "LIVESPEC_AI_ARC_APP_ID": "github_app_id",
    "LIVESPEC_AI_ARC_INSTALLATION_ID": "github_app_installation_id",
    "LIVESPEC_AI_ARC_PRIVATE_KEY": "github_app_private_key",
}

# The stand-in kubectl. A Secret is a state file `<ns>__<name>` holding one
# `data.<key>=<base64>` line per key, which is also what `create --dry-run=client
# -o yaml` prints and `replace -f -` stores. Every call appends its argv, joined
# by the unit separator, to $FAKE_KUBECTL_LOG.
_FAKE_KUBECTL = r"""#!/usr/bin/env bash
set -euo pipefail
{ printf '%s\x1f' "$@"; printf '\n'; } >> "$FAKE_KUBECTL_LOG"
case "$1" in
  create)
    name="$4"; ns=""
    shift 4
    for arg in "$@"; do
      case "$arg" in
        --from-file=*)
          spec="${arg#--from-file=}"; key="${spec%%=*}"; path="${spec#*=}"
          printf 'data.%s=%s\n' "$key" "$(base64 -w0 < "$path")" ;;
      esac
    done
    printf 'name=%s\n' "$name" ;;
  replace)
    body="$(cat)"
    name="$(printf '%s\n' "$body" | sed -n 's/^name=//p')"
    printf '%s\n' "$body" | grep '^data\.' > "$FAKE_STATE/arc-runners__${name}" ;;
  get)
    file="$FAKE_STATE/arc-runners__$3"
    [ -f "$file" ] || exit 1
    grep -c '^data\.' "$file" || true ;;
  *) echo "fake kubectl: unexpected verb $1" >&2; exit 2 ;;
esac
"""

_PERSONAL_BYTES = b"data.github_app_id=cGVyc29uYWw=\ndata.github_app_private_key=cGVyc29uYWwta2V5\n"
_ORG_BEFORE = b"data.github_app_id=b2xk\ndata.github_app_installation_id=b2xk\ndata.github_app_private_key=b2xk\n"


def _run(
    *, tmp_path: Path, env_values: dict[str, str]
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "kubectl"
    _ = fake.write_text(_FAKE_KUBECTL, encoding="utf-8")
    fake.chmod(0o755)
    state = tmp_path / "state"
    state.mkdir()
    _ = (state / f"{_NAMESPACE}__{_PERSONAL_SECRET}").write_bytes(_PERSONAL_BYTES)
    _ = (state / f"{_NAMESPACE}__{_ORG_SECRET}").write_bytes(_ORG_BEFORE)
    log = tmp_path / "kubectl.log"
    _ = log.write_text("", encoding="utf-8")
    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "HOME": str(tmp_path),
        "FAKE_KUBECTL_LOG": str(log),
        "FAKE_STATE": str(state),
        "ARC_ORG_PROJECTOR_KUBECONFIG": str(tmp_path / "kubeconfig"),
        **env_values,
    }
    result = subprocess.run(
        ["bash", str(_INJECTOR)], env=env, capture_output=True, text=True, check=False, timeout=60
    )
    return result, state, log


def _calls(*, log: Path) -> list[list[str]]:
    return [line.split("\x1f")[:-1] for line in log.read_text(encoding="utf-8").splitlines()]


def _assert_no_value_leaked(*, result: subprocess.CompletedProcess[str], log: Path) -> None:
    argv_text = log.read_text(encoding="utf-8")
    for name, value in _VALUES.items():
        for fragment in [value, *value.splitlines()]:
            if not fragment.startswith("-----"):
                assert fragment not in result.stdout, f"{name} leaked into stdout"
                assert fragment not in result.stderr, f"{name} leaked into stderr"
                assert fragment not in argv_text, f"{name} leaked into a kubectl argv"


def test_the_projection_writes_the_livespec_ai_arc_credential_and_leaves_the_personal_secret_unchanged(
    *, tmp_path: Path
) -> None:
    result, state, log = _run(tmp_path=tmp_path, env_values=dict(_VALUES))

    assert result.returncode == 0, result.stderr
    stored = dict(
        line.removeprefix("data.").split("=", 1)
        for line in (state / f"{_NAMESPACE}__{_ORG_SECRET}")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    assert {key: base64.b64decode(value).decode() for key, value in stored.items()} == {
        _KEY_OF[name]: value for name, value in _VALUES.items()
    }
    assert (state / f"{_NAMESPACE}__{_PERSONAL_SECRET}").read_bytes() == _PERSONAL_BYTES

    calls = _calls(log=log)
    # create and replace are the two ends of one pipeline, so they log in either order.
    assert sorted(call[0] for call in calls[:2]) == ["create", "replace"]
    assert calls[2][0] == "get"
    assert len(calls) == 3
    create = next(call for call in calls if call[0] == "create")
    assert create[1:4] == ["secret", "generic", _ORG_SECRET]
    assert create[create.index("--namespace") + 1] == _NAMESPACE
    from_files = sorted(arg.split("=", 2)[1] for arg in create if arg.startswith("--from-file="))
    assert from_files == sorted(_KEY_OF.values())
    assert not any(arg.startswith("--from-literal") for arg in create)
    assert calls[2][1:4] == ["secret", _ORG_SECRET, "-n"]
    assert calls[2][4] == _NAMESPACE
    assert all(arg != _PERSONAL_SECRET for call in calls for arg in call)
    _assert_no_value_leaked(result=result, log=log)


_MISSING_SETS = [
    combo for size in (1, 2, 3) for combo in itertools.combinations(sorted(_VALUES), size)
]


@pytest.mark.parametrize("how", ["absent", "empty"])
@pytest.mark.parametrize("missing", _MISSING_SETS, ids=lambda combo: "+".join(combo))
def test_the_projection_refuses_and_names_each_missing_value(
    *, tmp_path: Path, missing: tuple[str, ...], how: str
) -> None:
    env_values = {name: value for name, value in _VALUES.items() if name not in missing}
    if how == "empty":
        env_values.update(dict.fromkeys(missing, ""))

    result, state, log = _run(tmp_path=tmp_path, env_values=env_values)

    assert result.returncode != 0
    for name in missing:
        assert re.search(
            rf"\b{name}\b", result.stderr
        ), f"stderr does not name {name}: {result.stderr!r}"
    for name in set(_VALUES) - set(missing):
        assert f"{name} is missing" not in result.stderr
    assert _calls(log=log) == [], "a refused projection must not call kubectl at all"
    assert (state / f"{_NAMESPACE}__{_ORG_SECRET}").read_bytes() == _ORG_BEFORE
    assert (state / f"{_NAMESPACE}__{_PERSONAL_SECRET}").read_bytes() == _PERSONAL_BYTES
    _assert_no_value_leaked(result=result, log=log)


def test_the_projector_grant_is_get_update_patch_on_the_one_organization_secret() -> None:
    """The Role's whole rule set, from the committed bytes: one Secret, three verbs, no list."""
    text = _RBAC.read_text(encoding="utf-8")
    rules = text[text.index("rules:\n") : text.index("---")]
    assert rules == (
        "rules:\n"
        "  - apiGroups:\n"
        '      - ""\n'
        "    resources:\n"
        "      - secrets\n"
        "    resourceNames:\n"
        f"      - {_ORG_SECRET}\n"
        "    verbs:\n"
        "      - get\n"
        "      - update\n"
        "      - patch\n"
    )
    assert "  namespace: arc-runners\n" in text
    assert "    kind: User\n    name: arc-org-projector\n" in text


def test_the_unit_runs_the_launcher_as_the_dedicated_user_through_the_one_sudoers_command() -> None:
    """The unit's ExecStart and the sudoers rule render the SAME launch command, as a non-root user."""
    unit = (_ROLE / "templates" / "inject-github-app-secret-livespec-ai.service.j2").read_text(
        encoding="utf-8"
    )
    sudoers = (_ROLE / "templates" / "sudoers.d-arc-org-projector.j2").read_text(encoding="utf-8")
    defaults = (_ROLE / "defaults" / "main.yml").read_text(encoding="utf-8")

    assert "User={{ secret_reinjection_org_user }}\n" in unit
    assert "ExecStart=/usr/bin/sudo -n {{ secret_reinjection_org_launch_command }}\n" in unit
    assert "LoadCredential" not in unit
    assert (
        "{{ secret_reinjection_org_user }} ALL=(root) NOPASSWD: {{ secret_reinjection_org_launch_command }}\n"
        in sudoers
    )
    assert "secret_reinjection_org_user: arc-org-projector\n" in defaults
    assert "--consumer {{ secret_reinjection_org_consumer }}" in defaults
    assert "secret_reinjection_org_consumer: livespec-ai-arc\n" in defaults


_CONVERGE = _REPO_ROOT / "ci-runner" / "k3s" / "phase2" / "reconstruct" / "converge-ci-stack.sh"


def _converge_org_guard() -> str:
    """The converge's organization-Secret guard, sliced from the shipped script at its step-2 position."""
    text = _CONVERGE.read_text(encoding="utf-8")
    step2 = text.index('log "2. Fail-closed pre-gate')
    step3 = text.index('log "3. ', step2)
    start = text.index('ORG_ARC_SECRET="', step2)
    end = text.index("\nfi\n", start) + len("\nfi\n")
    assert (
        step2 < start < end <= step3
    ), "the org-Secret guard must sit inside step 2, before anything is applied"
    return text[start:end]


@pytest.mark.parametrize(("keys", "admitted"), [(None, False), (0, False), (2, False), (3, True)])
def test_the_converge_refuses_to_start_without_a_filled_organization_secret(
    *, tmp_path: Path, keys: int | None, admitted: bool
) -> None:
    """Absent, the empty placeholder, or a partial Secret each refuse; three keys pass."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "kubectl"
    answer = "exit 1" if keys is None else f"echo {keys}"
    _ = fake.write_text(
        f'#!/usr/bin/env bash\n[ "$1 $2 $3" = "get secret {_ORG_SECRET}" ] || exit 9\n{answer}\n',
        encoding="utf-8",
    )
    fake.chmod(0o755)
    script = tmp_path / "guard.sh"
    _ = script.write_text(
        f"set -euo pipefail\nRUNNERS_NAMESPACE={_NAMESPACE}\n{_converge_org_guard()}echo ADMITTED\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["bash", str(script)],
        env={"PATH": f"{bin_dir}:/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if admitted:
        assert result.returncode == 0, result.stdout + result.stderr
        assert "ADMITTED" in result.stdout
    else:
        assert result.returncode == 1
        assert "ADMITTED" not in result.stdout
        assert f"FATAL: secret {_ORG_SECRET}" in result.stdout


def test_a_normal_converge_never_runs_the_one_shot_organization_projection() -> None:
    """The one-shot block is gated on secret_reinjection_org_project_now, which defaults to false."""
    defaults = (_ROLE / "defaults" / "main.yml").read_text(encoding="utf-8")
    tasks = (_ROLE / "tasks" / "org_projection.yml").read_text(encoding="utf-8")
    assert "\nsecret_reinjection_org_project_now: false\n" in defaults
    block = tasks[
        tasks.index("- name: Run the organization projection once and prove it value-free\n") :
    ]
    gate = block[: block.index("  block:\n")]
    assert "    - secret_reinjection_org_project_now | bool\n" in gate
    assert "    - not ansible_check_mode\n" in gate
    started = block.index("state: started")
    assert block.index("secret_reinjection_personal_hash_before") < started
    assert "secret_reinjection_org_key_count.stdout | trim == '3'" in block[started:]

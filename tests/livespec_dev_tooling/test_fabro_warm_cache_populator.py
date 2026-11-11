"""The Fabro fork has a separately-budgeted, profile-matched sccache warm pass."""

from __future__ import annotations

from pathlib import Path

__all__: list[str] = []

_ROOT = Path(__file__).resolve().parents[2]
_WARM_CACHE = _ROOT / "ci-runner" / "k3s" / "phase2" / "warm-cache"
_FABRO_CRONJOB = _WARM_CACHE / "warm-cache-fabro-cronjob.yaml"
_CONVERGE = _WARM_CACHE / "converge-warm-cache.sh"
_FABRO_VALUES = _ROOT / "ci-runner" / "k3s" / "phase2" / "arc" / "values-fabro.yaml"


def test_fabro_is_warmed_by_its_own_guarded_populator_with_the_gate_profiles() -> None:
    """The large fork cannot consume the shared pass, and its warm keys match its jobs."""
    script = (_WARM_CACHE / "warm-cache-fabro-populate.sh").read_text(encoding="utf-8")
    cronjob = _FABRO_CRONJOB.read_text(encoding="utf-8")

    assert "# warm-cache: exclude" in _FABRO_VALUES.read_text(encoding="utf-8")
    assert "name: warm-cache-populate-fabro" in cronjob
    assert 'schedule: "5 * * * *"' in cronjob
    assert "activeDeadlineSeconds: 14400" in cronjob
    assert "warm-cache-fabro-populate.sh" in cronjob
    assert "SCCACHE_FABRO_MIN_FREE_BYTES" in cronjob
    assert "4294967296" in cronjob

    for branch, command in (
        ("factory-integration", "cargo +nightly-2026-04-14 clippy --workspace --all-targets"),
        (
            "factory-integration",
            "tini -s -- cargo +1.97.1 nextest run --locked --workspace --profile ci",
        ),
        (
            "carrier-candidate-registered-20261023",
            "cargo +1.97.1 dev build --release -p fabro-cli",
        ),
    ):
        assert branch in script
        assert command in script

    assert "NODE_ENV=production" in script
    assert 'JOB_WORK_ROOT="${JOB_WORK_ROOT:-/__w}"' in script
    assert 'build_dir="${JOB_WORK_ROOT}/fabro/fabro"' in script
    assert "INFO memory" in script
    assert "SCCACHE_FABRO_MIN_FREE_BYTES" in script
    assert "used_memory" in script
    assert "maxmemory" in script
    assert "server has setup with ReadWrite" in script
    assert "SCCACHE_REDIS_RW_MODE=READ_WRITE" in script


def test_the_headroom_read_is_made_as_the_default_user_not_the_writer() -> None:
    """The writer ACL has no +info, so INFO must use the default user the ACL grants it to."""
    script = (_WARM_CACHE / "warm-cache-fabro-populate.sh").read_text(encoding="utf-8")
    acl = (
        _ROOT / "ci-runner" / "k3s" / "phase2" / "sccache" / "converge-sccache-redis.sh"
    ).read_text(encoding="utf-8")

    assert "-@all +@read +@connection +info" in acl
    assert "redis_default_raw INFO memory" in script
    assert "redis_raw INFO memory" not in script


def test_the_fabro_pass_waits_for_the_regular_pass_instead_of_overlapping_it() -> None:
    """The two CronJobs have separate concurrency scopes, so the fork pass reads the regular Jobs."""
    script = (_WARM_CACHE / "warm-cache-fabro-populate.sh").read_text(encoding="utf-8")
    cronjob = _FABRO_CRONJOB.read_text(encoding="utf-8")

    assert "regular_pass_active" in script
    assert "/apis/batch/v1/namespaces/" in script
    assert "kind: Role\n" in cronjob
    assert "name: warm-cache-populate-fabro-job-reader" in cronjob
    assert 'resources: ["jobs"]' in cronjob
    assert 'verbs: ["get", "list"]' in cronjob
    assert "kind: RoleBinding" in cronjob
    assert "FABRO_WAIT_FOR_REGULAR_SECONDS" in script


def test_the_converge_mounts_the_fabro_populator_script() -> None:
    """The mounted ConfigMap, not a disk copy, is the reader the CronJob executes."""
    converge = _CONVERGE.read_text(encoding="utf-8")
    assert (
        "--from-file=warm-cache-fabro-populate.sh=${SCRIPT_DIR}/warm-cache-fabro-populate.sh"
        in converge
    )

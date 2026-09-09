import ast
import json
from pathlib import Path

import pytest

from ..collect import FailedJobNotFound, NoFailedStep, collect_failed_job

PYTEST_LOG = "collected 3 items\n=================== FAILURES ===================\ntest_api.py::test_shape\n"

DEFAULT_STEPS = [
    {"number": 1, "name": "Checkout", "conclusion": "success"},
    {"number": 2, "name": "Run pytest", "conclusion": "failure"},
    {"number": 3, "name": "Upload coverage", "conclusion": "failure"},
]


def _files(
    tmp_path: Path,
    *,
    steps: list[dict] | None = None,
    log: str = PYTEST_LOG,
) -> tuple[Path, Path]:
    """Write the two files the workflow hands to Python: `gh api` jobs and `gh run view`."""
    payload = {
        "jobs": [
            {
                "id": 122,
                "run_id": 456,
                "workflow_name": "CI",
                "name": "lint",
                "steps": None,
            },
            {
                "id": 123,
                "run_id": 456,
                "workflow_name": "CI",
                "name": "tests (3.11)",
                "steps": DEFAULT_STEPS if steps is None else steps,
            },
        ]
    }
    jobs_file = tmp_path / "jobs.json"
    jobs_file.write_text(json.dumps(payload), encoding="utf-8")
    log_file = tmp_path / "failed.log"
    log_file.write_text(log, encoding="utf-8")
    return jobs_file, log_file


def _collect(tmp_path: Path, *, job_name: str = "tests (3.11)", **kwargs):
    jobs_file, log_file = _files(tmp_path, **kwargs)
    return collect_failed_job(jobs_file=jobs_file, log_file=log_file, job_name=job_name)


def test_jobs_payload_and_job_name_resolve_to_failure_identity(tmp_path: Path):
    outcome = _collect(tmp_path)

    assert outcome.failure.workflow == "CI"
    assert outcome.failure.job == "tests (3.11)"
    assert outcome.failure.step == "Run pytest"
    assert outcome.failure.job_id == "123"
    assert outcome.failure.run_id == "456"


def test_first_failed_step_is_the_lowest_numbered_failure(tmp_path: Path):
    steps = [
        {"number": 3, "name": "Upload coverage", "conclusion": "failure"},
        {"number": 2, "name": "Run pytest", "conclusion": "failure"},
        {"number": 1, "name": "Checkout", "conclusion": "success"},
    ]

    outcome = _collect(tmp_path, steps=steps)

    assert outcome.failure.step == "Run pytest"


def test_logs_are_available_as_local_files(tmp_path: Path):
    outcome = _collect(tmp_path)

    assert [path.read_text(encoding="utf-8") for path in outcome.log_files] == [PYTEST_LOG]


def test_pytest_step_name_is_a_test_failure(tmp_path: Path):
    outcome = _collect(tmp_path, log="no cues here")

    assert outcome.is_test_failure


def test_test_output_in_logs_is_a_test_failure(tmp_path: Path):
    steps = [{"number": 1, "name": "Run checks", "conclusion": "failure"}]

    outcome = _collect(tmp_path, steps=steps)

    assert outcome.is_test_failure


def test_test_output_is_not_credited_to_an_earlier_failed_step(tmp_path: Path):
    steps = [
        {"number": 1, "name": "Run ruff", "conclusion": "failure"},
        {"number": 2, "name": "Run pytest", "conclusion": "failure"},
    ]

    outcome = _collect(tmp_path, steps=steps)

    assert outcome.failure.step == "Run ruff"
    assert not outcome.is_test_failure


def test_lint_step_without_test_output_is_not_a_test_failure(tmp_path: Path):
    steps = [{"number": 1, "name": "Run ruff", "conclusion": "failure"}]

    outcome = _collect(tmp_path, steps=steps, log="ruff: 3 errors")

    assert not outcome.is_test_failure


def test_missing_job_name_fails_clearly(tmp_path: Path):
    with pytest.raises(FailedJobNotFound, match="deploy"):
        _collect(tmp_path, job_name="deploy")


def test_job_without_steps_fails_clearly(tmp_path: Path):
    with pytest.raises(NoFailedStep, match="lint"):
        _collect(tmp_path, job_name="lint")


def test_job_without_a_failed_step_fails_clearly(tmp_path: Path):
    steps = [{"number": 1, "name": "Run pytest", "conclusion": "success"}]

    with pytest.raises(NoFailedStep, match="tests"):
        _collect(tmp_path, steps=steps)


_NETWORK_MODULES = {"http", "httpx", "requests", "urllib", "urllib3", "socket"}


def test_the_package_never_reaches_the_network(tmp_path: Path):
    """ADR 0003, enforced: the workflow calls the GitHub API, this package never does.

    `subprocess` is exempt on purpose — `tools/repo.py` runs local git with it.
    """
    package = Path(__file__).resolve().parent.parent
    offenders = []
    for source in package.rglob("*.py"):
        if source.parent.name == "tests":
            continue
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if name.split(".")[0] in _NETWORK_MODULES:
                    offenders.append(f"{source.name}: {name}")

    assert offenders == []

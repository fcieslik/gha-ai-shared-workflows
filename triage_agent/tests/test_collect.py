from pathlib import Path

import pytest

from ..collect import collect_failed_job
from ..github import (
    FailedJobNotFound,
    GitHubPort,
    JobStep,
    NoFailedStep,
    SealedPortError,
    WorkflowJob,
    WorkflowRun,
)

PYTEST_LOG = "collected 3 items\n=================== FAILURES ===================\ntest_api.py::test_shape\n"


class FakeGitHub(GitHubPort):
    """In-memory stand-in for the GitHub REST API, recording every call."""

    def __init__(
        self,
        *,
        runs: dict[str, WorkflowRun] | None = None,
        jobs: dict[str, list[WorkflowJob]] | None = None,
        logs: dict[str, str] | None = None,
    ) -> None:
        self.runs = runs or {}
        self.jobs = jobs or {}
        self.logs = logs or {}
        self.calls: list[str] = []

    def _fetch_run(self, run_id: str) -> WorkflowRun | None:
        self.calls.append(f"run:{run_id}")
        return self.runs.get(run_id)

    def _fetch_jobs(self, run_id: str) -> list[WorkflowJob]:
        self.calls.append(f"jobs:{run_id}")
        return self.jobs.get(run_id, [])

    def _fetch_job_logs(self, job_id: str) -> str:
        self.calls.append(f"logs:{job_id}")
        return self.logs.get(job_id, "")


def _github(*, steps: list[JobStep] | None = None, log: str = PYTEST_LOG) -> FakeGitHub:
    steps = steps or [
        JobStep(number=1, name="Checkout", conclusion="success"),
        JobStep(number=2, name="Run pytest", conclusion="failure"),
        JobStep(number=3, name="Upload coverage", conclusion="failure"),
    ]
    return FakeGitHub(
        runs={"456": WorkflowRun(run_id="456", workflow="CI")},
        jobs={
            "456": [
                WorkflowJob(job_id="122", name="lint", steps=()),
                WorkflowJob(job_id="123", name="tests (3.11)", steps=tuple(steps)),
            ]
        },
        logs={"123": log},
    )


def _collect(github: FakeGitHub, log_dir: Path, job_name: str = "tests (3.11)"):
    return collect_failed_job(
        github=github, run_id="456", job_name=job_name, log_dir=log_dir
    )


def test_run_id_and_job_name_resolve_to_failure_identity(tmp_path: Path):
    outcome = _collect(_github(), tmp_path)

    assert outcome.failure.workflow == "CI"
    assert outcome.failure.job == "tests (3.11)"
    assert outcome.failure.step == "Run pytest"
    assert outcome.failure.job_id == "123"
    assert outcome.failure.run_id == "456"


def test_first_failed_step_is_the_lowest_numbered_failure(tmp_path: Path):
    steps = [
        JobStep(number=3, name="Upload coverage", conclusion="failure"),
        JobStep(number=2, name="Run pytest", conclusion="failure"),
        JobStep(number=1, name="Checkout", conclusion="success"),
    ]

    outcome = _collect(_github(steps=steps), tmp_path)

    assert outcome.failure.step == "Run pytest"


def test_logs_are_stored_as_local_files(tmp_path: Path):
    outcome = _collect(_github(), tmp_path)

    assert [path.read_text() for path in outcome.log_files] == [PYTEST_LOG]
    assert all(path.parent == tmp_path for path in outcome.log_files)


def test_github_port_is_sealed_once_collect_returns(tmp_path: Path):
    github = _github()

    _collect(github, tmp_path)

    with pytest.raises(SealedPortError):
        github.list_jobs("456")


def test_github_port_is_sealed_even_when_collect_fails(tmp_path: Path):
    github = _github()

    with pytest.raises(FailedJobNotFound):
        _collect(github, tmp_path, job_name="nope")

    with pytest.raises(SealedPortError):
        github.list_jobs("456")


def test_pytest_step_name_is_a_test_failure(tmp_path: Path):
    outcome = _collect(_github(log="no cues here"), tmp_path)

    assert outcome.is_test_failure


def test_test_output_in_logs_is_a_test_failure(tmp_path: Path):
    steps = [JobStep(number=1, name="Run checks", conclusion="failure")]

    outcome = _collect(_github(steps=steps), tmp_path)

    assert outcome.is_test_failure


def test_lint_step_without_test_output_is_not_a_test_failure(tmp_path: Path):
    steps = [JobStep(number=1, name="Run ruff", conclusion="failure")]

    outcome = _collect(_github(steps=steps, log="ruff: 3 errors"), tmp_path)

    assert not outcome.is_test_failure


def test_missing_run_fails_clearly(tmp_path: Path):
    github = FakeGitHub()

    with pytest.raises(FailedJobNotFound, match="456"):
        _collect(github, tmp_path)


def test_missing_job_name_fails_clearly(tmp_path: Path):
    with pytest.raises(FailedJobNotFound, match="deploy"):
        _collect(_github(), tmp_path, job_name="deploy")


def test_job_without_a_failed_step_fails_clearly(tmp_path: Path):
    steps = [JobStep(number=1, name="Run pytest", conclusion="success")]

    with pytest.raises(NoFailedStep, match="tests"):
        _collect(_github(steps=steps), tmp_path)

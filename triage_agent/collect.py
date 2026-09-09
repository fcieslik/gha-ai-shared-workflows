"""Collect: resolve the Failed Job, store its logs, classify it as a Test Failure."""

import re
from pathlib import Path

from .github import (
    FailedJobNotFound,
    GitHubPort,
    JobStep,
    NoFailedStep,
    WorkflowJob,
)
from .models import CollectOutcome, FailureIdentity


def collect_failed_job(
    *,
    github: GitHubPort,
    run_id: str,
    job_name: str,
    log_dir: Path,
) -> CollectOutcome:
    """Resolve `run_id` + `job_name` into a Failed Job with logs on disk.

    Seals the GitHub port on the way out — success or failure — so that no later
    node can reach GitHub (ADR 0003).
    """
    try:
        run = github.get_run(run_id)
        if run is None:
            raise FailedJobNotFound(f"run {run_id} was not found")
        job = _resolve_job(github.list_jobs(run_id), run_id, job_name)
        step = _first_failed_step(job)
        logs = github.get_job_logs(job.job_id)
    finally:
        github.seal()

    log_file = _store_logs(log_dir, job.job_id, logs)
    return CollectOutcome(
        failure=FailureIdentity(
            workflow=run.workflow,
            job=job.name,
            step=step.name,
            job_id=job.job_id,
            run_id=run.run_id,
        ),
        is_test_failure=_is_test_failure(step, logs),
        log_files=(log_file,),
    )


def _resolve_job(jobs: list[WorkflowJob], run_id: str, job_name: str) -> WorkflowJob:
    matches = [job for job in jobs if job.name == job_name]
    if len(matches) != 1:
        raise FailedJobNotFound(
            f"run {run_id} has {len(matches)} jobs named {job_name!r}, expected 1"
        )
    return matches[0]


def _first_failed_step(job: WorkflowJob) -> JobStep:
    failed = [step for step in job.steps if step.conclusion == "failure"]
    if not failed:
        raise NoFailedStep(f"job {job.name!r} has no failed step")
    return min(failed, key=lambda step: step.number)


def _store_logs(log_dir: Path, job_id: str, logs: str) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"job-{job_id}.log"
    log_file.write_text(logs)
    return log_file


_TEST_STEP_NAME = re.compile(r"pytest|py\.test|\btests?\b", re.IGNORECASE)
_TEST_LOG_CUES = ("=== FAILURES ===", "short test summary info")


def _is_test_failure(step: JobStep, logs: str) -> bool:
    """Deterministic classify: the step name first, its log output as a fallback."""
    if _TEST_STEP_NAME.search(step.name):
        return True
    return any(cue in logs for cue in _TEST_LOG_CUES)

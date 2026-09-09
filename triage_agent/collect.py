"""Collect: read the Failed Job from files the workflow fetched, classify it.

The workflow runs `gh api .../jobs` and `gh run view --log-failed` before Python
starts, so this package never talks to GitHub (ADR 0003).
"""

import json
import re
from pathlib import Path
from typing import Any

from .models import CollectOutcome, FailureIdentity


class CollectError(Exception):
    """A Failed Job could not be resolved from the collected files."""


class FailedJobNotFound(CollectError):
    """The jobs file names no job matching the requested name."""


class NoFailedStep(CollectError):
    """The job exists but has no failed step to investigate."""


def collect_failed_job(
    *,
    jobs_file: Path,
    log_file: Path,
    job_name: str,
) -> CollectOutcome:
    """Resolve the Failed Job from a jobs API payload plus its failed-step logs."""
    job = _resolve_job(jobs_file, job_name)
    failed_steps = _failed_steps(job, job_name)
    step = min(failed_steps, key=lambda step: step["number"])
    logs = log_file.read_text(encoding="utf-8")
    return CollectOutcome(
        failure=FailureIdentity(
            workflow=str(job["workflow_name"]),
            job=str(job["name"]),
            step=str(step["name"]),
            job_id=str(job["id"]),
            run_id=str(job["run_id"]),
        ),
        is_test_failure=_is_test_failure(
            str(step["name"]), logs, failed_steps=len(failed_steps)
        ),
        log_files=(log_file,),
    )


def _resolve_job(jobs_file: Path, job_name: str) -> dict[str, Any]:
    payload = json.loads(jobs_file.read_text(encoding="utf-8"))
    matches = [job for job in payload["jobs"] if job["name"] == job_name]
    if len(matches) != 1:
        raise FailedJobNotFound(
            f"{len(matches)} jobs named {job_name!r} in {jobs_file.name}, expected 1"
        )
    return matches[0]


def _failed_steps(job: dict[str, Any], job_name: str) -> list[dict[str, Any]]:
    failed = [step for step in job.get("steps") or [] if step["conclusion"] == "failure"]
    if not failed:
        raise NoFailedStep(f"job {job_name!r} has no failed step")
    return failed


_TEST_STEP_NAME = re.compile(r"pytest|py\.test", re.IGNORECASE)
_TEST_LOG_CUES = ("=== FAILURES ===", "short test summary info")


def _is_test_failure(step_name: str, logs: str, *, failed_steps: int) -> bool:
    """Deterministic classify: the step name first, the failed-step logs as a fallback.

    `--log-failed` covers every failed step, so test output in it only belongs to
    this step when it is the job's only failed step.
    """
    if _TEST_STEP_NAME.search(step_name):
        return True
    if failed_steps > 1:
        return False
    return any(cue in logs for cue in _TEST_LOG_CUES)

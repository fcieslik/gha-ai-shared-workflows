"""Read-only GitHub access for collect, the only node allowed to use it (ADR 0003)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


class CollectError(Exception):
    """A Failed Job could not be resolved from the given run and job name."""


class FailedJobNotFound(CollectError):
    """The run does not exist, or names no job matching the requested name."""


class NoFailedStep(CollectError):
    """The job exists but has no failed step to investigate."""


class SealedPortError(RuntimeError):
    """The GitHub port was used after collect finished."""


@dataclass(frozen=True)
class WorkflowRun:
    run_id: str
    workflow: str


@dataclass(frozen=True)
class JobStep:
    number: int
    name: str
    conclusion: str


@dataclass(frozen=True)
class WorkflowJob:
    job_id: str
    name: str
    steps: tuple[JobStep, ...]


class GitHubPort(ABC):
    """Injection point for GitHub reads.

    Every public method stops working once `seal()` is called, so a specialist
    holding a reference to the port after collect cannot reach GitHub with it.
    """

    _sealed = False

    def seal(self) -> None:
        self._sealed = True

    def get_run(self, run_id: str) -> WorkflowRun | None:
        self._refuse_when_sealed()
        return self._fetch_run(run_id)

    def list_jobs(self, run_id: str) -> list[WorkflowJob]:
        self._refuse_when_sealed()
        return self._fetch_jobs(run_id)

    def get_job_logs(self, job_id: str) -> str:
        self._refuse_when_sealed()
        return self._fetch_job_logs(job_id)

    def _refuse_when_sealed(self) -> None:
        if self._sealed:
            raise SealedPortError("the GitHub port is sealed after collect")

    @abstractmethod
    def _fetch_run(self, run_id: str) -> WorkflowRun | None: ...

    @abstractmethod
    def _fetch_jobs(self, run_id: str) -> list[WorkflowJob]: ...

    @abstractmethod
    def _fetch_job_logs(self, job_id: str) -> str: ...

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

TriageDecision = Literal["AUTO_FIX", "HUMAN_REVIEW", "UNRESOLVED"]
Risk = Literal["LOW", "MEDIUM", "HIGH"]


@dataclass(frozen=True)
class FailureIdentity:
    workflow: str
    job: str
    step: str
    job_id: str
    run_id: str


@dataclass(frozen=True)
class CollectOutcome:
    failure: FailureIdentity
    is_test_failure: bool
    log_files: tuple[Path, ...] = ()


@dataclass(frozen=True)
class RootCause:
    summary: str
    details: str


@dataclass(frozen=True)
class RecommendedFix:
    description: str


@dataclass(frozen=True)
class AssessProposal:
    proposed_decision: TriageDecision
    confidence: float
    risk: Risk
    root_cause: RootCause | None
    evidence: list[str]
    affected_files: list[str]
    recommended_fix: RecommendedFix | None


@dataclass(frozen=True)
class TriageResult:
    proposed_decision: TriageDecision
    decision: TriageDecision
    gate_reason: str | None
    failure: FailureIdentity

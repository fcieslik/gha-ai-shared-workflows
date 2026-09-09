from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

TriageDecision = Literal["AUTO_FIX", "HUMAN_REVIEW", "UNRESOLVED"]
Risk = Literal["LOW", "MEDIUM", "HIGH"]
HypothesisStatus = Literal["proposed", "committed", "discarded"]


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
class Hypothesis:
    """A ranked working guess. Only assess may promote one to the Root Cause."""

    summary: str
    rank: int
    status: HypothesisStatus = "proposed"


@dataclass(frozen=True)
class LogFindings:
    observations: list[str]


@dataclass(frozen=True)
class Localization:
    affected_files: list[str]
    observations: list[str]


@dataclass(frozen=True)
class EvidenceRound:
    evidence: list[str]
    needs_more: bool


@dataclass(frozen=True)
class Investigation:
    """Working state handed to each specialist. Never leaves the graph."""

    failure: FailureIdentity
    log_files: tuple[Path, ...] = ()
    log_findings: LogFindings | None = None
    localization: Localization | None = None
    hypotheses: tuple[Hypothesis, ...] = ()
    evidence: tuple[str, ...] = ()
    evidence_loop_iterations: int = 0


@dataclass(frozen=True)
class AssessProposal:
    proposed_decision: TriageDecision
    confidence: float
    risk: Risk
    root_cause: RootCause | None
    evidence: list[str]
    affected_files: list[str]
    recommended_fix: RecommendedFix | None
    hypotheses: list[Hypothesis] = field(default_factory=list)
    validation: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TriageResult:
    proposed_decision: TriageDecision
    decision: TriageDecision
    gate_reason: str | None
    failure: FailureIdentity
    confidence: float = 0.0
    risk: Risk = "HIGH"
    root_cause: RootCause | None = None
    hypotheses: list[Hypothesis] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    affected_files: list[str] = field(default_factory=list)
    recommended_fix: RecommendedFix | None = None
    validation: list[str] = field(default_factory=list)
    evidence_loop_iterations: int = 0

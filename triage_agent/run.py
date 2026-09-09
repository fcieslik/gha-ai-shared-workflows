from collections.abc import Callable
from dataclasses import dataclass, replace

from .models import (
    AssessProposal,
    CollectOutcome,
    EvidenceRound,
    Hypothesis,
    Investigation,
    Localization,
    LogFindings,
    TriageDecision,
    TriageResult,
)

MAX_EVIDENCE_ROUNDS = 3


@dataclass(frozen=True)
class Specialists:
    """The five LLM nodes of the investigation graph, injected as callables."""

    inspect_logs: Callable[[Investigation], LogFindings]
    localize: Callable[[Investigation], Localization]
    form_hypothesis: Callable[[Investigation], list[Hypothesis]]
    gather_evidence: Callable[[Investigation], EvidenceRound]
    assess: Callable[[Investigation], AssessProposal]


def run_triage(
    *,
    collect: Callable[[], CollectOutcome],
    specialists: Specialists,
) -> TriageResult:
    """collect → inspect_logs → localize → form_hypothesis → evidence loop → assess → gate."""
    outcome = collect()
    if not outcome.is_test_failure:
        return TriageResult(
            proposed_decision="HUMAN_REVIEW",
            decision="HUMAN_REVIEW",
            gate_reason="out_of_mvp_scope",
            failure=outcome.failure,
        )
    investigation = _investigate(outcome, specialists)
    return apply_gate(specialists.assess(investigation), investigation)


def _investigate(outcome: CollectOutcome, specialists: Specialists) -> Investigation:
    state = Investigation(failure=outcome.failure, log_files=outcome.log_files)
    state = replace(state, log_findings=specialists.inspect_logs(state))
    state = replace(state, localization=specialists.localize(state))
    state = replace(state, hypotheses=tuple(specialists.form_hypothesis(state)))
    return _gather_evidence(state, specialists.gather_evidence)


def _gather_evidence(
    state: Investigation, gather: Callable[[Investigation], EvidenceRound]
) -> Investigation:
    """At most MAX_EVIDENCE_ROUNDS rounds, then assess is forced by returning."""
    for _ in range(MAX_EVIDENCE_ROUNDS):
        round_ = gather(state)
        state = replace(
            state,
            evidence=state.evidence + tuple(round_.evidence),
            evidence_loop_iterations=state.evidence_loop_iterations + 1,
        )
        if not round_.needs_more:
            break
    return state


def apply_gate(proposal: AssessProposal, investigation: Investigation) -> TriageResult:
    decision, reason = _policy(proposal)
    return TriageResult(
        proposed_decision=proposal.proposed_decision,
        decision=decision,
        gate_reason=reason,
        failure=investigation.failure,
        confidence=proposal.confidence,
        risk=proposal.risk,
        # An UNRESOLVED result has no Root Cause by definition; the ranked
        # Hypotheses survive so a human can see what was considered.
        root_cause=None if decision == "UNRESOLVED" else proposal.root_cause,
        hypotheses=proposal.hypotheses or list(investigation.hypotheses),
        evidence=proposal.evidence,
        affected_files=proposal.affected_files,
        recommended_fix=proposal.recommended_fix,
        validation=proposal.validation,
        evidence_loop_iterations=investigation.evidence_loop_iterations,
    )


_PERMISSIVENESS = {"UNRESOLVED": 0, "HUMAN_REVIEW": 1, "AUTO_FIX": 2}


def _policy(proposal: AssessProposal) -> tuple[TriageDecision, str | None]:
    eligible, reason = _eligibility(proposal)
    proposed = proposal.proposed_decision
    if _PERMISSIVENESS[proposed] < _PERMISSIVENESS[eligible]:
        return proposed, f"proposed decision is {proposed}"
    return eligible, reason


_LOCKFILES = frozenset(
    {
        "Cargo.lock",
        "Gemfile.lock",
        "Pipfile.lock",
        "composer.lock",
        "go.sum",
        "package-lock.json",
        "pnpm-lock.yaml",
        "poetry.lock",
        "uv.lock",
        "yarn.lock",
    }
)
_DENY_DIRS = (".github/", "helm/", "k8s/", "terraform/")


def _eligibility(proposal: AssessProposal) -> tuple[TriageDecision, str | None]:
    if proposal.root_cause is None:
        return "UNRESOLVED", "root cause is missing"
    if proposal.confidence < 0.8:
        return "HUMAN_REVIEW", "confidence below 0.8"
    if proposal.risk != "LOW":
        return "HUMAN_REVIEW", "risk is not LOW"
    if len(proposal.evidence) < 2:
        return "HUMAN_REVIEW", "fewer than 2 evidence items"
    if not 1 <= len(proposal.affected_files) <= 3:
        return "HUMAN_REVIEW", "affected files empty or exceed 3"
    if proposal.recommended_fix is None:
        return "HUMAN_REVIEW", "recommended fix is missing"
    for path in proposal.affected_files:
        if _is_denied(path):
            return "HUMAN_REVIEW", f"affected path matches deny list: {path}"
    return "AUTO_FIX", None


def _is_denied(path: str) -> bool:
    normalized = path.replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    name = normalized.rsplit("/", 1)[-1]
    if name in _LOCKFILES:
        return True
    if name == ".env" or name.startswith(".env.") or name.endswith(".env"):
        return True
    if "secret" in name.lower():
        return True
    return any(
        normalized == directory.rstrip("/")
        or normalized.startswith(directory)
        or f"/{directory}" in f"/{normalized}"
        for directory in _DENY_DIRS
    )

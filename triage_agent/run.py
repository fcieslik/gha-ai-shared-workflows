from collections.abc import Callable

from .models import (
    AssessProposal,
    CollectOutcome,
    FailureIdentity,
    TriageDecision,
    TriageResult,
)


def run_triage(
    *,
    collect: Callable[[], CollectOutcome],
    assess: Callable[[CollectOutcome], AssessProposal],
) -> TriageResult:
    outcome = collect()
    if not outcome.is_test_failure:
        return TriageResult(
            proposed_decision="HUMAN_REVIEW",
            decision="HUMAN_REVIEW",
            gate_reason="out_of_mvp_scope",
            failure=outcome.failure,
        )
    return apply_gate(assess(outcome), outcome.failure)


def apply_gate(proposal: AssessProposal, failure: FailureIdentity) -> TriageResult:
    decision, reason = _policy(proposal)
    return TriageResult(
        proposed_decision=proposal.proposed_decision,
        decision=decision,
        gate_reason=reason,
        failure=failure,
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

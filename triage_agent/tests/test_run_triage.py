from dataclasses import replace

import pytest

from .. import run_triage
from ..models import (
    AssessProposal,
    CollectOutcome,
    FailureIdentity,
    RecommendedFix,
    RootCause,
)


def _failure() -> FailureIdentity:
    return FailureIdentity(
        workflow="CI",
        job="lint",
        step="ruff",
        job_id="1",
        run_id="2",
    )


def test_non_test_failure_is_human_review_without_assess():
    assess_calls = []

    def collect() -> CollectOutcome:
        return CollectOutcome(failure=_failure(), is_test_failure=False)

    def assess(outcome: CollectOutcome):
        assess_calls.append(outcome)
        raise AssertionError("assess must not run")

    result = run_triage(collect=collect, assess=assess)

    assert result.decision == "HUMAN_REVIEW"
    assert result.proposed_decision == "HUMAN_REVIEW"
    assert result.gate_reason == "out_of_mvp_scope"
    assert result.failure == _failure()
    assert assess_calls == []


def _test_failure() -> FailureIdentity:
    return FailureIdentity(
        workflow="CI",
        job="tests",
        step="pytest",
        job_id="10",
        run_id="20",
    )


def _eligible_proposal() -> AssessProposal:
    return AssessProposal(
        proposed_decision="AUTO_FIX",
        confidence=0.91,
        risk="LOW",
        root_cause=RootCause(summary="assertion mismatch", details="field X became Y"),
        evidence=["failing assertion in tests/test_api.py", "recent commit changed schema"],
        affected_files=["tests/test_api.py"],
        recommended_fix=RecommendedFix(description="update the assertion"),
    )


def test_eligible_test_failure_stays_auto_fix():
    def collect() -> CollectOutcome:
        return CollectOutcome(failure=_test_failure(), is_test_failure=True)

    def assess(outcome: CollectOutcome) -> AssessProposal:
        assert outcome.is_test_failure
        return _eligible_proposal()

    result = run_triage(collect=collect, assess=assess)

    assert result.decision == "AUTO_FIX"
    assert result.proposed_decision == "AUTO_FIX"
    assert result.gate_reason is None
    assert result.failure == _test_failure()


def _run_test_failure(proposal: AssessProposal):
    def collect() -> CollectOutcome:
        return CollectOutcome(failure=_test_failure(), is_test_failure=True)

    def assess(outcome: CollectOutcome) -> AssessProposal:
        return proposal

    return run_triage(collect=collect, assess=assess)


def test_missing_root_cause_is_unresolved_even_when_auto_fix_proposed():
    result = _run_test_failure(replace(_eligible_proposal(), root_cause=None))

    assert result.proposed_decision == "AUTO_FIX"
    assert result.decision == "UNRESOLVED"
    assert result.gate_reason == "root cause is missing"


def test_gate_does_not_upgrade_human_review_to_auto_fix():
    result = _run_test_failure(
        replace(_eligible_proposal(), proposed_decision="HUMAN_REVIEW")
    )

    assert result.proposed_decision == "HUMAN_REVIEW"
    assert result.decision == "HUMAN_REVIEW"
    assert result.gate_reason == "proposed decision is HUMAN_REVIEW"


def test_gate_does_not_upgrade_unresolved_to_auto_fix():
    result = _run_test_failure(
        replace(_eligible_proposal(), proposed_decision="UNRESOLVED")
    )

    assert result.proposed_decision == "UNRESOLVED"
    assert result.decision == "UNRESOLVED"
    assert result.gate_reason == "proposed decision is UNRESOLVED"


def test_ineligible_auto_fix_is_human_review():
    cases = [
        (replace(_eligible_proposal(), confidence=0.79), "confidence below 0.8"),
        (replace(_eligible_proposal(), risk="MEDIUM"), "risk is not LOW"),
        (replace(_eligible_proposal(), risk="HIGH"), "risk is not LOW"),
        (
            replace(_eligible_proposal(), evidence=["only one observation"]),
            "fewer than 2 evidence items",
        ),
        (
            replace(_eligible_proposal(), affected_files=[]),
            "affected files empty or exceed 3",
        ),
        (
            replace(
                _eligible_proposal(),
                affected_files=["a.py", "b.py", "c.py", "d.py"],
            ),
            "affected files empty or exceed 3",
        ),
        (
            replace(_eligible_proposal(), recommended_fix=None),
            "recommended fix is missing",
        ),
        (
            replace(_eligible_proposal(), affected_files=[".github/workflows/ci.yml"]),
            "affected path matches deny list: .github/workflows/ci.yml",
        ),
        (
            replace(_eligible_proposal(), affected_files=[".env"]),
            "affected path matches deny list: .env",
        ),
        (
            replace(_eligible_proposal(), affected_files=["poetry.lock"]),
            "affected path matches deny list: poetry.lock",
        ),
        (
            replace(_eligible_proposal(), affected_files=["terraform/main.tf"]),
            "affected path matches deny list: terraform/main.tf",
        ),
        (
            replace(_eligible_proposal(), affected_files=["k8s/deploy.yaml"]),
            "affected path matches deny list: k8s/deploy.yaml",
        ),
        (
            replace(_eligible_proposal(), affected_files=["helm/chart.yaml"]),
            "affected path matches deny list: helm/chart.yaml",
        ),
    ]
    for proposal, reason in cases:
        result = _run_test_failure(proposal)
        assert result.proposed_decision == "AUTO_FIX", reason
        assert result.decision == "HUMAN_REVIEW", reason
        assert result.gate_reason == reason


def test_github_port_is_unusable_by_anything_after_collect(tmp_path):
    from ..collect import collect_failed_job
    from ..github import SealedPortError
    from .test_collect import _github

    github = _github()

    def collect() -> CollectOutcome:
        return collect_failed_job(
            github=github, run_id="456", job_name="tests (3.11)", log_dir=tmp_path
        )

    def assess(outcome: CollectOutcome) -> AssessProposal:
        github.list_jobs("456")
        raise AssertionError("assess reached GitHub after collect")

    with pytest.raises(SealedPortError):
        run_triage(collect=collect, assess=assess)


def _recording_assess(calls: list):
    def assess(outcome: CollectOutcome) -> AssessProposal:
        calls.append(outcome)
        raise AssertionError("assess must not run")

    return assess


def _collect_from_github(github, tmp_path):
    from ..collect import collect_failed_job

    def collect() -> CollectOutcome:
        return collect_failed_job(
            github=github, run_id="456", job_name="tests (3.11)", log_dir=tmp_path
        )

    return collect


def test_collected_test_failure_carries_its_identity_to_the_result(tmp_path):
    from .test_collect import _github

    result = run_triage(
        collect=_collect_from_github(_github(), tmp_path),
        assess=lambda outcome: _eligible_proposal(),
    )

    assert result.decision == "AUTO_FIX"
    assert result.failure == FailureIdentity(
        workflow="CI", job="tests (3.11)", step="Run pytest", job_id="123", run_id="456"
    )


def test_collected_non_test_failure_is_out_of_mvp_scope(tmp_path):
    from ..github import JobStep
    from .test_collect import _github

    github = _github(
        steps=[JobStep(number=1, name="Run ruff", conclusion="failure")],
        log="ruff: 3 errors",
    )
    assess_calls = []

    result = run_triage(
        collect=_collect_from_github(github, tmp_path),
        assess=_recording_assess(assess_calls),
    )

    assert result.decision == "HUMAN_REVIEW"
    assert result.gate_reason == "out_of_mvp_scope"
    assert result.failure.step == "Run ruff"
    assert assess_calls == []


def test_missing_job_fails_before_any_specialist_runs(tmp_path):
    from ..collect import collect_failed_job
    from ..github import FailedJobNotFound
    from .test_collect import _github

    assess_calls = []

    def collect() -> CollectOutcome:
        return collect_failed_job(
            github=_github(), run_id="456", job_name="deploy", log_dir=tmp_path
        )

    with pytest.raises(FailedJobNotFound):
        run_triage(
            collect=collect, assess=_recording_assess(assess_calls)
        )

    assert assess_calls == []

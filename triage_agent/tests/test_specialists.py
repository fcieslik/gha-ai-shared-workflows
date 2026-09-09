from pathlib import Path

import pytest

pytest.importorskip("agents", reason="the agents extra is not installed")

from ..models import (  # noqa: E402
    CollectOutcome,
    FailureIdentity,
    Hypothesis,
    Investigation,
    LogFindings,
)
from ..specialists import (  # noqa: E402
    AssessOutput,
    brief,
    build_agents,
    default_specialists,
)
from ..tools import LogTools, RepoTools  # noqa: E402

LOG_TOOLS = {"read_log_slice", "search_logs"}
REPO_TOOLS = {"list_dir", "read_file", "grep", "git_log", "git_diff", "git_show"}


def _agents(tmp_path: Path):
    return build_agents(
        log_tools=LogTools([tmp_path / "job-1.log"]), repo_tools=RepoTools(tmp_path)
    )


def _names(agent) -> set[str]:
    return {tool.name for tool in agent.tools}


def test_inspect_logs_may_only_touch_logs(tmp_path: Path):
    assert _names(_agents(tmp_path).inspect_logs) == LOG_TOOLS


def test_localize_may_only_touch_the_checkout_and_git(tmp_path: Path):
    assert _names(_agents(tmp_path).localize) == REPO_TOOLS


def test_gather_evidence_may_touch_logs_and_the_checkout(tmp_path: Path):
    assert _names(_agents(tmp_path).gather_evidence) == LOG_TOOLS | REPO_TOOLS


def test_form_hypothesis_and_assess_have_no_tools(tmp_path: Path):
    agents = _agents(tmp_path)

    assert agents.form_hypothesis.tools == []
    assert agents.assess.tools == []


def test_no_specialist_can_write_check_out_or_reach_github(tmp_path: Path):
    agents = _agents(tmp_path)
    granted = set().union(
        *(_names(getattr(agents, name)) for name in vars(agents))
    )

    assert granted == LOG_TOOLS | REPO_TOOLS


def test_assess_output_carries_the_whole_triage_result(tmp_path: Path):
    assert _agents(tmp_path).assess.output_type is AssessOutput
    assert set(AssessOutput.model_fields) == {
        "proposed_decision",
        "confidence",
        "risk",
        "root_cause",
        "evidence",
        "affected_files",
        "recommended_fix",
        "hypotheses",
        "validation",
    }


def test_brief_carries_the_accumulated_state_into_the_prompt():
    state = Investigation(
        failure=FailureIdentity(
            workflow="CI", job="tests", step="Run pytest", job_id="1", run_id="2"
        ),
        log_findings=LogFindings(observations=["assertion failed"]),
        hypotheses=(Hypothesis(summary="schema drift", rank=1),),
        evidence=("recent commit changed the schema",),
        evidence_loop_iterations=1,
    )

    text = brief(state)

    assert "Run pytest" in text
    assert "assertion failed" in text
    assert "1. schema drift" in text
    assert "recent commit changed the schema" in text


def test_default_specialists_are_the_sdk_agents_bound_to_this_run(tmp_path: Path):
    log_file = tmp_path / "job-1.log"
    log_file.write_text("boom\n", encoding="utf-8")
    outcome = CollectOutcome(
        failure=FailureIdentity(
            workflow="CI", job="tests", step="Run pytest", job_id="1", run_id="2"
        ),
        is_test_failure=True,
        log_files=(log_file,),
    )

    specialists = default_specialists(outcome=outcome, workspace=tmp_path)

    assert all(
        callable(getattr(specialists, node))
        for node in (
            "inspect_logs",
            "localize",
            "form_hypothesis",
            "gather_evidence",
            "assess",
        )
    )

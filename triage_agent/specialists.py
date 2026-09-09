"""Production specialists: OpenAI Agents SDK agents, one per LLM node.

Importing this module needs the `agents` extra; `import triage_agent` does not,
so tests inject fakes at the `run_triage` seam without the SDK or a model call.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from agents import Agent, Runner, Tool, function_tool
from pydantic import BaseModel

from .models import (
    AssessProposal,
    CollectOutcome,
    EvidenceRound,
    Hypothesis,
    Investigation,
    Localization,
    LogFindings,
    RecommendedFix,
    RootCause,
)
from .run import Specialists
from .tools import LogTools, RepoTools

INSPECT_LOGS_INSTRUCTIONS = (
    "You inspect CI logs for a failed job. Read and search the collected log files "
    "to describe what actually failed. Do not guess about the repository."
)
LOCALIZE_INSTRUCTIONS = (
    "You locate the code involved in a CI failure. Read the checkout and the "
    "bounded git history. Report affected files, not fixes."
)
FORM_HYPOTHESIS_INSTRUCTIONS = (
    "You propose several ranked hypotheses for why the job failed, using only the "
    "state given to you. Rank 1 is the most likely. Do not commit to one."
)
GATHER_EVIDENCE_INSTRUCTIONS = (
    "You look for observations that support or weaken the ranked hypotheses. Say "
    "whether another round would meaningfully change the picture."
)
ASSESS_INSTRUCTIONS = (
    "You commit the investigation to a Triage Result. Propose a decision, "
    "confidence, risk, evidence, affected files and a recommended fix. Commit a "
    "root cause only when the evidence supports it; otherwise leave it out and "
    "propose UNRESOLVED. You have no tools: decide on what you were given."
)


class HypothesisOutput(BaseModel):
    summary: str
    rank: int
    status: Literal["proposed", "committed", "discarded"] = "proposed"

class RootCauseOutput(BaseModel):
    summary: str
    details: str

class LogFindingsOutput(BaseModel):
    observations: list[str]

class LocalizationOutput(BaseModel):
    affected_files: list[str]
    observations: list[str]

class HypothesesOutput(BaseModel):
    hypotheses: list[HypothesisOutput]

class EvidenceRoundOutput(BaseModel):
    evidence: list[str]
    needs_more: bool

class AssessOutput(BaseModel):
    proposed_decision: Literal["AUTO_FIX", "HUMAN_REVIEW", "UNRESOLVED"]
    confidence: float
    risk: Literal["LOW", "MEDIUM", "HIGH"]
    root_cause: RootCauseOutput | None
    evidence: list[str]
    affected_files: list[str]
    recommended_fix: str | None
    hypotheses: list[HypothesisOutput]
    validation: list[str]


@dataclass(frozen=True)
class SpecialistAgents:
    """The five agents, exposed so their tool allowlists are inspectable."""

    inspect_logs: Agent[Any]
    localize: Agent[Any]
    form_hypothesis: Agent[Any]
    gather_evidence: Agent[Any]
    assess: Agent[Any]


def build_agents(
    *, log_tools: LogTools, repo_tools: RepoTools, model: str | None = None
) -> SpecialistAgents:
    """Build the five SDK agents, each with only the tools its node may use."""
    log_allowlist: list[Tool] = [
        function_tool(log_tools.read_log_slice),
        function_tool(log_tools.search_logs),
    ]
    repo_allowlist: list[Tool] = [
        function_tool(repo_tools.list_dir),
        function_tool(repo_tools.read_file),
        function_tool(repo_tools.grep),
        function_tool(repo_tools.git_log),
        function_tool(repo_tools.git_diff),
        function_tool(repo_tools.git_show),
    ]
    return SpecialistAgents(
        inspect_logs=Agent(
            name="inspect_logs",
            instructions=INSPECT_LOGS_INSTRUCTIONS,
            tools=log_allowlist,
            output_type=LogFindingsOutput,
            model=model,
        ),
        localize=Agent(
            name="localize",
            instructions=LOCALIZE_INSTRUCTIONS,
            tools=repo_allowlist,
            output_type=LocalizationOutput,
            model=model,
        ),
        form_hypothesis=Agent(
            name="form_hypothesis",
            instructions=FORM_HYPOTHESIS_INSTRUCTIONS,
            tools=[],
            output_type=HypothesesOutput,
            model=model,
        ),
        gather_evidence=Agent(
            name="gather_evidence",
            instructions=GATHER_EVIDENCE_INSTRUCTIONS,
            tools=[*log_allowlist, *repo_allowlist],
            output_type=EvidenceRoundOutput,
            model=model,
        ),
        assess=Agent(
            name="assess",
            instructions=ASSESS_INSTRUCTIONS,
            tools=[],
            output_type=AssessOutput,
            model=model,
        ),
    )


def default_specialists(
    *, outcome: CollectOutcome, workspace: Path, model: str | None = None
) -> Specialists:
    """The specialists Triage runs with unless a caller injects its own.

    Assembled per run rather than once: the log tools are bound to the files
    collect downloaded, so they cannot exist before collect has run.
    """
    return openai_specialists(
        log_tools=LogTools(outcome.log_files),
        repo_tools=RepoTools(workspace),
        model=model,
    )


def openai_specialists(
    *, log_tools: LogTools, repo_tools: RepoTools, model: str | None = None
) -> Specialists:
    """The default specialists used when nothing is injected."""
    agents = build_agents(log_tools=log_tools, repo_tools=repo_tools, model=model)

    def inspect_logs(state: Investigation) -> LogFindings:
        output = _run(agents.inspect_logs, state, LogFindingsOutput)
        return LogFindings(observations=list(output.observations))

    def localize(state: Investigation) -> Localization:
        output = _run(agents.localize, state, LocalizationOutput)
        return Localization(
            affected_files=list(output.affected_files),
            observations=list(output.observations),
        )

    def form_hypothesis(state: Investigation) -> list[Hypothesis]:
        output = _run(agents.form_hypothesis, state, HypothesesOutput)
        return [_hypothesis(item) for item in output.hypotheses]

    def gather_evidence(state: Investigation) -> EvidenceRound:
        output = _run(agents.gather_evidence, state, EvidenceRoundOutput)
        return EvidenceRound(
            evidence=list(output.evidence), needs_more=output.needs_more
        )

    def assess(state: Investigation) -> AssessProposal:
        output = _run(agents.assess, state, AssessOutput)
        return AssessProposal(
            proposed_decision=output.proposed_decision,
            confidence=output.confidence,
            risk=output.risk,
            root_cause=(
                RootCause(
                    summary=output.root_cause.summary,
                    details=output.root_cause.details,
                )
                if output.root_cause
                else None
            ),
            evidence=list(output.evidence),
            affected_files=list(output.affected_files),
            recommended_fix=(
                RecommendedFix(description=output.recommended_fix)
                if output.recommended_fix
                else None
            ),
            hypotheses=[_hypothesis(item) for item in output.hypotheses],
            validation=list(output.validation),
        )

    return Specialists(
        inspect_logs=inspect_logs,
        localize=localize,
        form_hypothesis=form_hypothesis,
        gather_evidence=gather_evidence,
        assess=assess,
    )


def _run(agent: Agent[Any], state: Investigation, output_type: type) -> Any:
    result = Runner.run_sync(agent, brief(state))
    return result.final_output_as(output_type)


def _hypothesis(item: "HypothesisOutput") -> Hypothesis:
    return Hypothesis(summary=item.summary, rank=item.rank, status=item.status)


def brief(state: Investigation) -> str:
    """The investigation state as prompt text — the only input a specialist gets."""
    failure = state.failure
    lines = [
        f"Workflow: {failure.workflow}",
        f"Job: {failure.job}",
        f"First failed step: {failure.step}",
        f"Collected log files: {', '.join(path.name for path in state.log_files) or 'none'}",
    ]
    if state.log_findings:
        lines.append("Log findings:")
        lines += [f"- {item}" for item in state.log_findings.observations]
    if state.localization:
        lines.append(
            f"Affected files so far: {', '.join(state.localization.affected_files) or 'none'}"
        )
        lines += [f"- {item}" for item in state.localization.observations]
    if state.hypotheses:
        lines.append("Ranked hypotheses:")
        lines += [f"- {item.rank}. {item.summary}" for item in state.hypotheses]
    if state.evidence:
        lines.append("Evidence so far:")
        lines += [f"- {item}" for item in state.evidence]
    lines.append(f"Evidence rounds completed: {state.evidence_loop_iterations}")
    return "\n".join(lines)

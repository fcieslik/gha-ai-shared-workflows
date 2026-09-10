# Fix failures workflow

Status: implemented

## Problem Statement

Współdzielony workflow nie może sam nasłuchiwać ukończenia każdego workflowu w repozytorium konsumenta: `workflow_run` wymaga nazw workflowów i działa w tym samym repozytorium. Potrzebny jest reużywalny etap zbierający dane z nieudanego pipeline'u bez z góry znanych nazw workflowów.

## Solution

Repozytorium konsumenta wywołuje workflow `Fix failures` jako końcowy job z warunkiem `failure()`, przekazując identyfikator i próbę własnego runu oraz klucz współbieżności. Współdzielony workflow zbiera dane bieżącej próby; nowsze diagnostyki dla tego samego workflowu i refu anulują jeszcze trwającą starszą diagnostykę.

Job diagnostyczny ma odczytać wejścia od caller workflowu, znaleźć wszystkie nieudane joby bieżącej próby i pobrać ich logi. Pozostaje wyłącznie do odczytu; dane z GitHub są zbierane deterministycznie przed ewentualną analizą lub naprawą.

## User Stories

1. As an operator, I want any consumer pipeline to call the shared workflow after a failure, so that workflow names do not need to be known in advance.
2. As an operator, I want successful, cancelled, and otherwise non-failed pipeline runs to skip the reusable job, so that diagnostic capacity is not spent on non-failures.
3. As an operator, I want newer diagnostics for the same source workflow and ref to cancel active older diagnostics, so that current failures take precedence.
4. As an operator, I want independent workflows and refs to be handled independently, so that unrelated failures do not cancel each other.
5. As a diagnostic job, I want the caller to provide its failed run identifier, attempt, workflow identity, and branch or revision fallback, so that I can retrieve the correct evidence without a forwarding job.
6. As a diagnostic job, I want to inspect all failed jobs and failed steps from the current attempt, so that parallel or independent causes are not hidden by the first failure.
7. As a diagnostic job, I want to retrieve the corresponding job logs, so that a later analysis or repair stage receives concrete failure evidence.
8. As a security-conscious maintainer, I want the diagnostic stage to have only read permissions, so that a failure originating from a pull request cannot grant write capability.
9. As a maintainer, I want GitHub API access to remain at the deterministic collection boundary, so that later analysis does not receive a GitHub token or make uncontrolled repository calls.
10. As a maintainer, I want cancellation of stale diagnostic work, so that repeated pushes do not waste runner time.

## Implementation Decisions

- Use `workflow_call`, not `workflow_run`; the consumer's terminal `if: failure()` job determines when the shared workflow runs.
- Require the caller to pass the run identifier, attempt, workflow name, ref, and revision fallback as inputs.
- Scope concurrency by source workflow identity and source ref; when the ref is unavailable, use the source revision as the grouping fallback. Newer work cancels in-progress work in the same group.
- Use the caller-provided run identifier and attempt to list jobs for the current attempt, select every failed job, and retrieve each selected job's logs.
- Grant the diagnostic stage only the Actions read permission. It must not receive write permissions or secrets intended for a repair stage.
- Keep GitHub API calls in the deterministic collection boundary before any later analysis, consistent with the existing decision that model-facing components do not call GitHub directly.
- Do not check out untrusted pull-request code in the diagnostic stage.

## Testing Decisions

- Add a manual fixture pipeline and a fixture command that deterministically fails.
- The fixture's terminal job invokes the shared workflow locally after `failure()` and passes the caller metadata.
- Validate both workflow files with a GitHub Actions-compatible linter; manually dispatch the fixture in GitHub Actions to verify job and log collection.

## Out of Scope

- Generating or applying a code fix.
- Creating a pull request, pushing commits, or granting write permissions.
- LLM-based diagnosis, triage, decision gates, or human approval flows.
- Persisting logs as job outputs or artifacts for a later workflow.
- Observing repositories that do not opt in by adding a terminal reusable-workflow job.

## Further Notes

- The reusable workflow receives run metadata from its caller; failed-job details and logs are retrieved through the Actions API.
- Download URLs for logs are short-lived, so logs should be consumed within the diagnostic run rather than forwarded as job outputs.

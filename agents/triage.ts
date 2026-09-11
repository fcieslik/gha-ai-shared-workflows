import { randomUUID } from "node:crypto";
import { readFile } from "node:fs/promises";
import {
  Agent,
  run,
  setDefaultOpenAIKey,
  setTracingExportApiKey,
} from "@openai/agents";
import OpenAI from "openai";
import { TRIAGE_AGENT_INSTRUCTIONS } from "./instructions.ts";
import { type TriageVerdict, TriageVerdictSchema } from "./schema.ts";
import { runLogAnalyst } from "./subagents/log-analitics/main.ts";
import {
  loadErrorExcerpts,
  loadFailedJobs,
  withUploadedJobLogs,
} from "./subagents/log-analitics/utils.ts";

// Confidence levels the fixing agent may act on without a person checking the verdict first.
// The prompt caps confidence at medium until change and history data exist.
const FIX_CONFIDENCE_LEVELS: TriageVerdict["confidence"][] = ["high", "medium"];

async function main() {
  const apiKey = process.env.OPENAI_API_KEY!;
  setDefaultOpenAIKey(apiKey);
  setTracingExportApiKey(apiKey);

  const runContextPath = process.env.RUN_CONTEXT_PATH;
  if (!runContextPath) throw new Error("RUN_CONTEXT_PATH is not set");
  const runContext = JSON.parse(await readFile(runContextPath, "utf8"));

  const failedJobs = await loadFailedJobs();
  const excerpts = await loadErrorExcerpts();

  // Stage 1: the log analyst investigates the logs with its own tools and turn limit.
  const logAnalysis = await withUploadedJobLogs(
    new OpenAI({ apiKey }),
    failedJobs,
    (logFileIds) => runLogAnalyst(failedJobs, excerpts, logFileIds),
  );

  // Stage 2: the triage agent has no tools or handoffs, so it can only judge the findings.
  const triageAgent = new Agent({
    name: "Triage Agent",
    model: "gpt-5.6-terra",
    instructions: TRIAGE_AGENT_INSTRUCTIONS,
    outputType: TriageVerdictSchema,
  });

  const result = await run(
    triageAgent,
    [
      "<run_context>",
      JSON.stringify(runContext, null, 2),
      "</run_context>",
      "<failed_jobs>",
      JSON.stringify(
        failedJobs.map(({ id, name, failed_steps }) => ({
          id,
          name,
          failed_steps,
        })),
        null,
        2,
      ),
      "</failed_jobs>",
      "<log_findings>",
      JSON.stringify(logAnalysis, null, 2),
      "</log_findings>",
    ].join("\n"),
    { maxTurns: 1 },
  );

  const verdict = result.finalOutput;
  if (!verdict) throw new Error("Triage Agent gave no verdict.");

  // The report carries the collected data as is, so the fixing agent does not depend on the
  // model copying it correctly.
  const triageReport = {
    run_context: runContext,
    failed_jobs: failedJobs,
    log_analysis: logAnalysis,
    verdict,
    ready_for_fix:
      verdict.next_action === "fix" &&
      verdict.fix !== null &&
      FIX_CONFIDENCE_LEVELS.includes(verdict.confidence),
  };

  console.log(JSON.stringify(triageReport, null, 2));
}

// The output quotes CI logs, and the runner executes workflow commands such as ##[error]
// anywhere in a line, which rewrites the report in the step log and adds annotations.
// Pausing command processing keeps the output verbatim; the random token stops quoted log
// text from resuming it.
const resumeCommandsToken = randomUUID();
console.log(`::stop-commands::${resumeCommandsToken}`);
try {
  await main();
} catch (error) {
  // console.error prints the stack and any cause, e.g. an API or zod validation error.
  console.error("Triage failed:", error);
  // exitCode instead of exit() lets pending output flush before the step fails.
  process.exitCode = 1;
} finally {
  console.log(`::${resumeCommandsToken}::`);
}

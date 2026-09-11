import { randomUUID } from "node:crypto";
import { readFile } from "node:fs/promises";
import {
  Agent,
  run,
  setDefaultOpenAIKey,
  setTracingExportApiKey,
  shellTool,
} from "@openai/agents";
import OpenAI from "openai";
import { TRIAGE_AGENT_INSTRUCTIONS } from "./instructions.ts";
import { type TriageVerdict, TriageVerdictSchema } from "./schema.ts";
import { createSourceShell } from "./source-shell.ts";
import { runHistoryAnalyst } from "./subagents/history-analitics/main.ts";
import { runLogAnalyst } from "./subagents/log-analitics/main.ts";
import {
  loadErrorExcerpts,
  loadFailedJobs,
  withUploadedJobLogs,
} from "./subagents/log-analitics/utils.ts";

// Confidence levels the fixing agent may act on without a person checking the verdict first.
// Medium stays allowed because history and the repository checkout are optional, and without
// them the lead seldom has grounds for high.
const FIX_CONFIDENCE_LEVELS: TriageVerdict["confidence"][] = ["high", "medium"];
// Bounds model calls; each shell call takes a turn.
const TRIAGE_MAX_TURNS = 20;

async function main() {
  const apiKey = process.env.OPENAI_API_KEY!;
  setDefaultOpenAIKey(apiKey);
  setTracingExportApiKey(apiKey);

  const runContextPath = process.env.RUN_CONTEXT_PATH;
  if (!runContextPath) throw new Error("RUN_CONTEXT_PATH is not set");
  const runContext = JSON.parse(await readFile(runContextPath, "utf8"));

  const failedJobs = await loadFailedJobs();
  const excerpts = await loadErrorExcerpts();

  // Stage 1: the log and history analysts are independent, so they run in parallel.
  const [logAnalysis, historyAnalysis] = await Promise.all([
    withUploadedJobLogs(new OpenAI({ apiKey }), failedJobs, (logFileIds) =>
      runLogAnalyst(failedJobs, excerpts, logFileIds),
    ),
    // History is optional context: its failure leaves the lead without it instead of
    // stopping triage.
    runHistoryAnalyst(runContext).catch((error) => {
      console.error("History analyst failed:", error);
      return null;
    }),
  ]);

  // Stage 2: the triage agent judges the findings and may read the repository at the failed
  // commit through the shell (ADR 0005).
  const sourceShell = createSourceShell(process.env.SOURCE_CHECKOUT_PATH);
  // Recorded in the shell itself, so the forced verdict after the turn limit keeps them too.
  const shellCommands: string[] = [];
  const triageAgent = new Agent({
    name: "Triage Agent",
    model: "gpt-5.6-terra",
    instructions: TRIAGE_AGENT_INSTRUCTIONS,
    tools: [
      shellTool({
        shell: {
          run(action) {
            shellCommands.push(...action.commands);
            return sourceShell.run(action);
          },
        },
        needsApproval: false,
      }),
    ],
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
      "<history_findings>",
      JSON.stringify(historyAnalysis ?? "unavailable", null, 2),
      "</history_findings>",
    ].join("\n"),
    {
      maxTurns: TRIAGE_MAX_TURNS,
      errorHandlers: {
        // Out of turns: ask for the verdict once more from what the lead has read so far.
        async maxTurns({ runData }) {
          const finalAnswer = await run(
            triageAgent.clone({ modelSettings: { toolChoice: "none" } }),
            [
              ...runData.history,
              {
                role: "user",
                content:
                  "The shell budget is used up. Return your verdict from what you found so far.",
              },
            ],
            { maxTurns: 1 },
          );
          if (!finalAnswer.finalOutput) {
            throw new Error(
              "Triage Agent gave no verdict after its shell budget.",
            );
          }
          return { finalOutput: finalAnswer.finalOutput };
        },
      },
    },
  );

  const verdict = result.finalOutput;
  if (!verdict) throw new Error("Triage Agent gave no verdict.");

  // The report carries the collected data as is, so the fixing agent does not depend on the
  // model copying it correctly.
  const triageReport = {
    run_context: runContext,
    failed_jobs: failedJobs,
    log_analysis: logAnalysis,
    history_analysis: historyAnalysis,
    shell_commands: shellCommands,
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

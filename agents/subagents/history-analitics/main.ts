import { readFile } from "node:fs/promises";
import { Agent, run } from "@openai/agents";
import { HISTORY_ANALITICS_AGENT_INSTRUCTIONS } from "./instructions.ts";
import { HistoryAnalysisSchema } from "./schema.ts";

type FailedRun = { run_id: number; sha: string; created_at: string };

// Both files come from continue-on-error steps, so they may be absent, empty or in a degraded
// shape. The JSON goes to the model as is, and anything unreadable becomes "unavailable".
async function loadOptionalContextFile(envName: string): Promise<unknown> {
  const path = process.env[envName];
  if (!path) return "unavailable";
  try {
    return JSON.parse(await readFile(path, "utf8"));
  } catch {
    return "unavailable";
  }
}

export async function runHistoryAnalyst(failedRun: FailedRun) {
  const [recentRuns, changes] = await Promise.all([
    loadOptionalContextFile("RECENT_RUNS_PATH"),
    loadOptionalContextFile("CHANGES_SINCE_LAST_SUCCESS_PATH"),
  ]);

  const historyAnalyst = new Agent({
    name: "History analyst",
    model: "gpt-5.6-luna",
    // The SDK default for this model is no reasoning, which labelled a run of failures a
    // new_regression. Explicit settings replace the SDK defaults as a whole.
    modelSettings: { reasoning: { effort: "low" } },
    instructions: HISTORY_ANALITICS_AGENT_INSTRUCTIONS,
    outputType: HistoryAnalysisSchema,
  });

  const result = await run(
    historyAnalyst,
    [
      "<failed_run>",
      JSON.stringify(
        {
          run_id: failedRun.run_id,
          sha: failedRun.sha,
          created_at: failedRun.created_at,
        },
        null,
        2,
      ),
      "</failed_run>",
      "<recent_runs>",
      JSON.stringify(recentRuns, null, 2),
      "</recent_runs>",
      "<changes>",
      JSON.stringify(changes, null, 2),
      "</changes>",
    ].join("\n"),
    { maxTurns: 1 },
  );
  if (!result.finalOutput) {
    throw new Error("History analyst gave no final answer.");
  }
  return result.finalOutput;
}

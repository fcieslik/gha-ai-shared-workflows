import {
  Agent,
  codeInterpreterTool,
  type ModelSettings,
  retryPolicies,
  run,
  tool,
} from "@openai/agents";
import { z } from "zod";
import { LOG_ANALITICS_AGENT_INSTRUCTIONS } from "./instructions.ts";
import { FailureAnalysisSchema } from "./schema.ts";
import {
  type ErrorExcerpt,
  type FailedJob,
  jobLogFilename,
  readJobLogLines,
} from "./utils.ts";

const MAX_LOG_LINES_PER_READ = 200;
const DEFAULT_MODEL = "gpt-5.6-luna";
// Bounds model calls, not single tool calls: one turn can hold several parallel calls.
// With the forced answer after the limit a run makes at most MAX_TURNS + 1 model calls,
// which must stay within 10.
const MAX_TURNS = 8;
// Last turns before the limit in which the model is told to wrap up.
const WRAP_UP_TURNS = 2;

// Explicit settings replace the SDK defaults for the model as a whole, so reasoning and
// verbosity are set here as well.
const MODEL_SETTINGS: ModelSettings = {
  // The SDK default for this model is no reasoning; telling a root error from its
  // consequences across jobs needs some.
  reasoning: { effort: "low" },
  // The SDK default of low verbosity trims the fact lists the triage lead relies on.
  text: { verbosity: "medium" },
  // Several log ranges can be read in one turn; every turn counts towards maxTurns.
  parallelToolCalls: true,
  // Without a timeout a hung call holds the CI job until the job times out.
  timeoutMs: 120_000,
  temperature: 0.1,
  retry: {
    maxRetries: 3,
    backoff: {
      initialDelayMs: 1_000,
      maxDelayMs: 10_000,
      multiplier: 2,
      jitter: true,
    },
    policy: retryPolicies.any(
      retryPolicies.providerSuggested(),
      retryPolicies.networkError(),
      retryPolicies.httpStatus([429, 500, 502, 503, 504]),
    ),
  },
};

// logFileIds are the logs uploaded by withUploadedJobLogs.
export function createLogAnalyst(
  failedJobs: FailedJob[],
  logFileIds: string[],
) {
  const readJobLog = tool({
    name: "read_job_log",
    description:
      "Read a range of lines from a failed job's full log. Lines are 1-based and prefixed with their number.",
    parameters: z.object({
      job_id: z.number().int(),
      from_line: z.number().int(),
      to_line: z.number().int(),
    }),
    async execute({ job_id, from_line, to_line }) {
      // Look the path up by job id so the model can only read the collected logs.
      const job = failedJobs.find((failedJob) => failedJob.id === job_id);
      if (!job) return `No failed job with id ${job_id}.`;
      if (to_line < from_line) {
        return `to_line (${to_line}) must not be less than from_line (${from_line}).`;
      }
      const { lines, totalLines } = await readJobLogLines(
        job,
        from_line,
        Math.min(to_line, from_line + MAX_LOG_LINES_PER_READ - 1),
      );
      return `${lines.join("\n")}\n(log has ${totalLines} lines)`;
    },
  });

  return new Agent({
    name: "Log analyst",
    model: DEFAULT_MODEL,
    modelSettings: MODEL_SETTINGS,
    instructions: LOG_ANALITICS_AGENT_INSTRUCTIONS,
    tools: [
      readJobLog,
      codeInterpreterTool({
        container: {
          type: "auto",
          file_ids: logFileIds,
          // The model writes this code while reading untrusted logs.
          network_policy: { type: "disabled" },
        },
      }),
    ],
    outputType: FailureAnalysisSchema,
  });
}

export function formatLogAnalystInput(
  failedJobs: FailedJob[],
  excerpts: ErrorExcerpt[],
): string {
  return failedJobs
    .map((job) => {
      const excerpt =
        excerpts.find((candidate) => candidate.job_id === job.id)?.excerpt ??
        "(no excerpt collected)";
      return [
        `<job id="${job.id}" name="${job.name}">`,
        `Failed steps: ${job.failed_steps.join(", ")}`,
        `Log file: ${jobLogFilename(job.id)}`,
        "<excerpt>",
        excerpt,
        "</excerpt>",
        "</job>",
      ].join("\n");
    })
    .join("\n\n");
}

export async function runLogAnalyst(
  failedJobs: FailedJob[],
  excerpts: ErrorExcerpt[],
  logFileIds: string[],
) {
  const logAnalyst = createLogAnalyst(failedJobs, logFileIds);
  let turn = 0;
  const result = await run(
    logAnalyst,
    formatLogAnalystInput(failedJobs, excerpts),
    {
      maxTurns: MAX_TURNS,
      // Runs before every model call. The note goes into the instructions rather than the
      // input, so notes do not pile up in the history. It only steers; maxTurns still stops.
      callModelInputFilter: ({ modelData }) => {
        turn++;
        const turnsLeft = MAX_TURNS - turn;
        if (turnsLeft >= WRAP_UP_TURNS) return modelData;
        const note =
          turnsLeft === 0
            ? "This is your last turn: return your final answer now, without tools."
            : `Only ${turnsLeft} more turn(s) after this one: stop exploring, use tools only to confirm what you already suspect, then answer.`;
        return {
          ...modelData,
          instructions: `${modelData.instructions ?? ""}\n\n${note} List what you could not check in gaps.`,
        };
      },
      errorHandlers: {
        // Out of turns: ask for the answer once more so the findings so far are kept. Tools
        // stay declared, which keeps the recorded tool calls valid, but cannot be called.
        async maxTurns({ runData }) {
          const finalAnswer = await run(
            logAnalyst.clone({
              modelSettings: { ...MODEL_SETTINGS, toolChoice: "none" },
            }),
            [
              ...runData.history,
              {
                role: "user",
                content:
                  "The tool budget is used up. Return your final answer from what you found so far and list what you could not check in gaps.",
              },
            ],
            { maxTurns: 1 },
          );
          if (!finalAnswer.finalOutput) {
            throw new Error(
              "Log analyst gave no final answer after its tool budget.",
            );
          }
          return { finalOutput: finalAnswer.finalOutput };
        },
      },
    },
  );
  if (!result.finalOutput) throw new Error("Log analyst gave no final answer.");
  return result.finalOutput;
}

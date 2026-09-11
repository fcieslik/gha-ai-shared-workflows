import { z } from "zod";

// Facts point back at the log so the triage lead can tell a quote from an inference
// and re-read only that spot.
const LogQuote = z.object({
  job_id: z.number().int(),
  log_line: z.number().int().describe("Line number in the job's full log."),
  text: z.string().describe("Text quoted from the log."),
});

export const FailureAnalysisSchema = z.object({
  summary: z
    .string()
    .describe(
      "What each job ran and where it stopped, in two or three sentences.",
    ),
  root_error_candidate: z
    .object({ quote: LogQuote, reasoning: z.string() })
    .nullable()
    .describe(
      "The error that most likely caused the failure, or null if none is visible.",
    ),
  kind: z.enum([
    "test_assertion",
    "compile",
    "dependencies",
    "timeout_or_memory",
    "network",
    "secrets_or_permissions",
    "runner",
    "unknown",
  ]),
  errors: z
    .array(LogQuote)
    .describe("Every distinct error, including ones after the first."),
  warnings: z
    .array(LogQuote)
    .describe(
      "Warnings before the failure, such as deprecations, retries, fallbacks, or version changes.",
    ),
  environment: z
    .array(LogQuote)
    .describe(
      "Tool and runtime versions, runner image, and the commands that ran.",
    ),
  locations: z
    .array(
      z.object({
        path: z.string(),
        source_line: z.number().int().nullable(),
        job_id: z.number().int(),
        log_line: z.number().int(),
      }),
    )
    .describe(
      "File paths and lines from stack traces or tool output, " +
        "in repository's own code only. Skip node_modules, " +
        "language runtime, and runner.",
    ),
  failing_tests: z
    .array(
      z.object({
        name: z.string(),
        job_id: z.number().int(),
        log_line: z.number().int(),
      }),
    )
    .describe("Names of failing tests, if any."),
  flaky_signals: z
    .array(LogQuote)
    .describe(
      "Evidence of nondeterminism, such as timeouts, races, or network errors.",
    ),
  gaps: z
    .array(z.string())
    .describe(
      "What the logs do not show but would help, such as a truncated stack trace.",
    ),
  confidence: z
    .enum(["high", "medium", "low"])
    .describe("Confidence in root_error_candidate."),
});

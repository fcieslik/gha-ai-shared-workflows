import { z } from "zod";

// Points back at the log analyst's facts, so the fixing agent can trust a quote and a
// developer can check it in the CI log.
const Evidence = z.object({
  job_id: z.number().int(),
  log_line: z.number().int(),
  text: z.string().describe("Text quoted from the log analyst's findings."),
});

export const TriageVerdictSchema = z.object({
  verdict: z.enum([
    "code_regression",
    "flaky_test",
    "dependencies",
    "ci_config",
    "preexisting_failure",
    "infrastructure",
    "uncertain",
  ]),
  confidence: z.enum(["high", "medium", "low"]),
  confidence_reasons: z
    .array(z.string())
    .describe(
      "What supports the confidence level and what keeps it from being higher.",
    ),
  next_action: z
    .enum(["fix", "rerun", "investigate", "human"])
    .describe(
      "fix: a repository change should make the jobs pass; rerun: flaky or infrastructure; " +
        "investigate: follow_ups could change the verdict; human: needs a person.",
    ),
  summary: z
    .string()
    .describe(
      "Two or three sentences a developer can act on, citing job_id and log_line.",
    ),
  root_cause: z.object({
    description: z
      .string()
      .describe("What broke and why, as far as the evidence shows."),
    error: Evidence.nullable().describe(
      "The error the verdict rests on, or null if none is visible.",
    ),
  }),
  evidence: z
    .array(Evidence)
    .describe("Every fact from the findings that the verdict rests on."),
  fix: z
    .object({
      goal: z
        .string()
        .describe("The behaviour the fix must restore, in one sentence."),
      files: z
        .array(
          z.object({
            path: z.string(),
            line: z.number().int().nullable(),
            reason: z.string(),
          }),
        )
        .describe(
          "Repository files to inspect or change first, taken from the findings; never invented.",
        ),
      suggested_changes: z
        .array(z.string())
        .describe("Hypotheses of what to change, most likely first."),
      verification: z
        .array(z.string())
        .describe(
          "Commands and tests from the findings that must pass after the fix.",
        ),
      risks: z
        .array(z.string())
        .describe(
          "What the fix must not break, and alternative causes to rule out.",
        ),
    })
    .nullable()
    .describe(
      "Instructions for the fixing agent, which cannot see the CI logs; null unless next_action is fix.",
    ),
  follow_ups: z
    .array(
      z.object({
        // Only the log analyst exists so far; extend with history and changes (ADR 0004).
        agent: z.enum(["logs"]),
        request: z.string(),
      }),
    )
    .describe(
      "Precise checks the log analyst can still make in the collected logs; empty when none would change the verdict.",
    ),
  missing_context: z
    .array(z.string())
    .describe(
      "Data that was not collected but would change the verdict, such as the diff, run history or test reports.",
    ),
});

export type TriageVerdict = z.infer<typeof TriageVerdictSchema>;
